<template>
  <div class="batch-import-page">
    <div class="header">
      <h2>批量导入交易记录</h2>
    </div>

    <!-- 上传区域 -->
    <div class="compact-upload-section">
      <div class="upload-bar">
        <!-- 左侧上传图标 -->
        <el-upload
          class="upload-icon"
          action=""
          :auto-upload="false"
          :on-change="handleFileChange"
          :show-file-list="false"
          accept=".xlsx,.xls,.csv"
        >
          <el-icon class="upload-icon-inner"><upload /></el-icon>
        </el-upload>

        <!-- 中间文件信息 -->
        <div v-if="file" class="file-info-bar">
          <el-icon><document /></el-icon>
          <span class="file-name">{{ file.name }}</span>
        </div>
        <div v-else class="file-info-bar empty">
          请选择文件
        </div>

        <!-- 右侧确认按钮 -->
        <div class="confirm-btn">
          <el-button
            type="primary"
            :loading="loading"
            :disabled="!file || loading"
            @click="submitImport"
          >
            确认
          </el-button>
        </div>
      </div>
    </div>

    <!-- 身份验证错误提示 -->
    <div v-if="authError" class="auth-error">
      <el-alert
        title="身份验证失败"
        :description="authError"
        type="error"
        show-icon
        closable
        @close="authError = ''"
      />
      <el-button type="primary" @click="handleReLogin" style="margin-top: 10px">
        重新登录
      </el-button>
    </div>

    <!-- 预览表格 -->
    <div v-if="previewData.length > 0" class="preview-section">
      <h3>交易信息预览</h3>
      <el-table :data="previewData" border stripe style="width: 100%">
        <el-table-column prop="type" label="类型" width="100">
          <template #default="{row}">
            <el-tag :type="row.type === 'income' ? 'success' : 'danger'">
              {{ row.type === 'income' ? '收入' : '支出' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="金额" width="120" align="right">
          <template #default="{row}">
            {{ parseFloat(row.amount).toFixed(2) }}
          </template>
        </el-table-column>
        <el-table-column prop="date" label="日期" width="120"></el-table-column>
        <el-table-column prop="time" label="时间" width="100"></el-table-column>
        <el-table-column prop="description" label="描述"></el-table-column>
        <el-table-column prop="category" label="分类" width="120">
          <template #default="{row}">
            <el-tag>{{ row.category }}</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary" style="margin-top: 20px; text-align: right">
        <strong>合计金额: </strong>
        <span :class="totalAmount >= 0 ? 'income-amount' : 'expense-amount'">
          {{ Math.abs(totalAmount).toFixed(2) }}
          <span v-if="totalAmount >= 0">(收入)</span>
          <span v-else>(支出)</span>
        </span>
      </div>
    </div>

    <!-- 导入结果区域 -->
    <div v-if="results.length > 0" class="results-section">
      <h3>导入结果</h3>
      <el-table
        :data="results"
        stripe
        border
        v-loading="loading"
      >
      </el-table>

    </div>

    <!-- 在导入结果区域下方添加确认按钮 -->
    <div v-if="previewData.length > 0" class="confirm-import-section">
      <el-button
        type="primary"
        :loading="loading"
        @click="confirmImport"
        size="large"
        :disabled="isConfirmed || loading"
      >
        {{ isConfirmed ? '已确认' : `确认导入 ${previewData.length} 条记录` }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue';
import { useRouter } from 'vue-router';
import { useUserStore } from '../store/user';
import { ElMessage } from 'element-plus';
import { Upload, Document, Close } from '@element-plus/icons-vue';
import axios from 'axios';

const importMessage = ref('');

const router = useRouter();
const previewData = ref([]);
const authError = ref(''); // 存储身份验证错误信息

// 计算属性：计算总金额
const totalAmount = computed(() => {
  return previewData.value.reduce((sum, item) => {
    const amount = parseFloat(item.amount) || 0;
    return item.type === 'income' ? sum + amount : sum - amount;
  }, 0);
});

const userStore = useUserStore();
const axiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 300000,
  headers: {
    'Content-Type': 'multipart/form-data',
    'Accept': 'application/json'
  }
});

// 添加请求拦截器用于Token管理
axiosInstance.interceptors.request.use(config => {
  const token = localStorage.getItem('token') || sessionStorage.getItem('token');
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`;
  } else {
    // 如果没有token，显示错误信息
    authError.value = '用户未登录或登录已过期';
  }
  return config;
}, error => {
  return Promise.reject(error);
});

// 添加响应拦截器处理401错误
axiosInstance.interceptors.response.use(
  response => response,
  error => {
    if (error.response && error.response.status === 401) {
      authError.value = '身份验证失败，请重新登录';
      // 清除无效的token
      localStorage.removeItem('token');
      sessionStorage.removeItem('token');
    }
    return Promise.reject(error);
  }
);

// 状态管理
const file = ref(null);
const loading = ref(false);
const progress = ref(0);
const results = ref([]);
const isConfirmed = ref(false);

// 方法
const handleFileChange = (uploadFile) => {
  // 清除之前的错误信息
  authError.value = '';

  const allowedTypes = [
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/csv',
    'application/octet-stream'
  ];
  const allowedExtensions = ['.xlsx', '.xls', '.csv'];

  if (!allowedTypes.includes(uploadFile.raw.type)) {
    const fileExtension = uploadFile.name.split('.').pop().toLowerCase();
    if (!allowedExtensions.includes('.' + fileExtension)) {
      ElMessage.error('请上传 Excel 文件 (.xlsx, .xls, .csv)');
      return;
    }
  }

  file.value = uploadFile.raw;
  previewData.value = []; // 清除旧的预览数据
  results.value = [];
  progress.value = 0;
};

const removeFile = () => {
  file.value = null;
  previewData.value = [];
  results.value = [];
  progress.value = 0;
};

const handleReLogin = () => {
  // 清除所有存储的token
  localStorage.removeItem('token');
  sessionStorage.removeItem('token');

  // 跳转到登录页面
  router.push('/login');
};

const submitImport = async () => {
  isConfirmed.value = false; // 重置确认状态
  if (!file.value) {
    ElMessage.warning('请先选择文件');
    return;
  }

  // 检查token是否存在
  const token = localStorage.getItem('token') || sessionStorage.getItem('token');
  if (!token) {
    authError.value = '用户未登录，请先登录';
    return;
  }

  try {
    loading.value = true;
    progress.value = 0;
    results.value = [];
    authError.value = ''; // 清除之前的错误信息

    const formData = new FormData();
    formData.append('file', file.value);

    const response = await axiosInstance.post('/chat/batch-import', formData);

    if (response.data && response.data.extracted_info) {
      previewData.value = response.data.extracted_info.map(item => ({
        ...item,
        amount: typeof item.amount === 'number' ? item.amount : parseFloat(item.amount) || 0,
        date: item.date || new Date().toISOString().split('T')[0],
        time: item.time || '00:00',
        category: item.category || '未分类'
      }));

      if (response.data.message) {
        ElMessage.info(response.data.message);
      }
    } else {
      ElMessage.error('未能从文件中识别出有效的交易信息');
    }
  } catch (error) {
    console.error('导入失败:', error);

    // 如果不是401错误，显示其他错误信息
    if (error.response?.status !== 401) {
      ElMessage.error(`导入失败: ${error.response?.data?.detail || error.message || '未知错误'}`);
    }
  } finally {
    loading.value = false;
    progress.value = 100;
  }
};

const confirmImport = async () => {
  try {
    loading.value = true;
    const requestData = {
      confirmed: true,
      transactions: previewData.value.map(item => ({
        amount: parseFloat(item.amount),
        type: item.type,
        description: item.description,
        category: item.category,
        date: item.date,
        time: item.time || '00:00' // 确保时间有默认值
      }))
    };
    // 创建新的axios实例，避免使用全局的multipart/form-data配置
    const jsonAxios = axios.create({
      baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('token') || sessionStorage.getItem('token')}`
      }
    });
    console.log('发送的数据:', JSON.stringify(requestData, null, 2));

    const response = await jsonAxios.post('/chat/batch-confirm', requestData);

    if (response.data && response.data.message) {
       ElMessage.success(response.data.message);
       isConfirmed.value = true;
    } else{
      ElMessage.error('服务器错误返回');
    }
  } catch (error) {
    console.error('确认导入失败:', error);
    if (error.response?.status === 401) {
      authError.value = '身份验证失败，请重新登录';
    } else {
      ElMessage.error(`确认导入失败: ${error.response?.data?.detail || error.message || '未知错误'}`);
    }
  } finally {
    loading.value = false;
  }
};
</script>

<style scoped>
/* 上传区域样式 */
.compact-upload-section {
  margin-top: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.compact-upload-area :deep(.el-upload-dragger) {
  padding: 20px 15px;
}


.preview-section {
  margin-top: 30px;
  padding: 20px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background-color: #fafafa;
}

/* 结果区域样式 */
.results-section {
  margin-top: 30px;
}

/* 身份验证错误样式 */
.auth-error {
  margin-top: 20px;
  max-width: 600px;
  margin-left: auto;
  margin-right: auto;
}

.compact-upload-section {
   margin: 20px 0;
}
.upload-bar {
  display: flex;
  align-items: center;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  padding: 8px 12px;
  background-color: #f5f7fa;
}

.upload-icon {
  margin-right: 12px;
}

.upload-icon-inner {
  font-size: 24px;
  color: #409eff;
  cursor: pointer;
}

.file-info-bar {
  flex: 1;
  display: flex;
  align-items: center;
  color: #606266;
}

.file-info-bar.empty {
  color: #c0c4cc;
}

.file-info-bar .el-icon {
  margin-right: 8px;
}

.file-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.confirm-btn {
  margin-left: 12px;
}

.confirm-import-section {
  margin-top: 30px;
  text-align: center;
  padding: 20px 0;
  border-top: 1px solid #ebeef5;
}

.preview-section {
  margin-top: 30px;
  padding: 20px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background-color: #fafafa;
}


.header {
  margin-bottom: 30px;
  text-align: center;
}


.file-name {
  margin-left: 10px;
  flex: 1;
}

.results-section {
  margin-top: 30px;
}

.summary {
  margin-top: 20px;
  display: flex;
  justify-content: center;
}

.summary-item span {
  display: block;
  font-size: 14px;
  color: #909399;
}

.summary-item strong {
  font-size: 18px;
}

.el-upload__text em {
  color: #409eff;
  font-style: normal;
}

</style>
<style scoped>.import-message {
  margin: 20px 0;
  max-width: 600px;
  margin-left: auto;
  margin-right: auto;
}
</style>