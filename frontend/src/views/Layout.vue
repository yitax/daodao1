<template>
  <div class="app-layout">
    <el-container>
      <el-aside width="200px" class="fixed-aside">
        <div class="sidebar">
          <div class="logo">
            <h2>叨叨记账</h2>
          </div>
          <el-menu
            router
            :default-active="$route.path"
            class="sidebar-menu"
            background-color="#3D6E59"
            text-color="#E3F2ED"
            active-text-color="#9BFFDA"
          >
            <el-menu-item index="/chat">
              <el-icon><ChatDotRound /></el-icon>
              <span>聊天记账</span>
            </el-menu-item>
            
            <el-menu-item index="/manual">
              <el-icon><EditPen /></el-icon>
              <span>手动记账</span>
            </el-menu-item>

            <el-menu-item index="/batch">
               <el-icon><Upload /></el-icon>
               <span>批量导入</span>
            </el-menu-item>

            <el-sub-menu index="/reports">
              <template #title>
                <el-icon><DataAnalysis /></el-icon>
                <span>财务报表</span>
              </template>
              <el-menu-item index="/reports/summary">
                <el-icon><TrendCharts /></el-icon>
                <span>收支总览</span>
              </el-menu-item>
              <el-menu-item index="/reports/daily">
                <el-icon><Calendar /></el-icon>
                <span>每日趋势</span>
              </el-menu-item>
              <el-menu-item index="/reports/category">
                <el-icon><PieChart /></el-icon>
                <span>分类排行</span>
              </el-menu-item>
              <el-menu-item index="/reports/ranking">
                <el-icon><SortUp /></el-icon>
                <span>明细排行</span>
              </el-menu-item>
              <el-menu-item index="/reports/ledger">
                <el-icon><Notebook /></el-icon>
                <span>每日报表</span>
              </el-menu-item>
            </el-sub-menu>
            
            <el-menu-item index="/spending-habits">
              <el-icon><Operation /></el-icon>
              <span>消费习惯分析</span>
            </el-menu-item>
            
            <el-sub-menu index="/settings">
              <template #title>
                <el-icon><Setting /></el-icon>
                <span>设置</span>
              </template>
              <el-menu-item index="/settings/personality">
                <el-icon><Avatar /></el-icon>
                <span>AI个性</span>
              </el-menu-item>
              <el-menu-item index="/settings/account">
                <el-icon><User /></el-icon>
                <span>账户设置</span>
              </el-menu-item>
            </el-sub-menu>
          </el-menu>
        </div>
      </el-aside>
      
      <el-container class="main-container">
        <el-header height="60px">
          <div class="header-content">
            <div class="left"></div>
            <div class="right">
              <el-dropdown @command="handleCommand">
                <span class="user-info">
                  <el-avatar :size="32" icon="User" />
                  <span class="username">{{ userStore.username }}</span>
                  <el-icon><ArrowDown /></el-icon>
                </span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="settings">账户设置</el-dropdown-item>
                    <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </div>
        </el-header>
        
        <el-main>
          <router-view />
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router';
import { useUserStore } from '../store/user';
import { ElMessageBox, ElMessage } from 'element-plus';
import { onMounted } from 'vue';
import {
  ChatDotRound,
  DataAnalysis,
  TrendCharts,
  Calendar,
  PieChart,
  SortUp,
  Notebook,
  Setting,
  Avatar,
  User,
  ArrowDown,
  EditPen,
  Operation, Upload
} from '@element-plus/icons-vue';

const router = useRouter();
const userStore = useUserStore();

// 组件加载时检查用户登录状态
onMounted(async () => {
  console.log('[Layout] 组件加载，检查用户登录状态');
  
  // 检查用户是否已登录
  if (!userStore.isLoggedIn) {
    console.log('[Layout] 用户未登录，尝试恢复会话');
    try {
      await userStore.checkAuth();
      
      // 恢复会话后再次检查登录状态
      if (!userStore.isLoggedIn) {
        console.log('[Layout] 恢复会话失败，重定向到登录页面');
        ElMessage.warning('请先登录');
        router.replace('/login');
      }
    } catch (error) {
      console.error('[Layout] 检查认证状态出错:', error);
      ElMessage.error('会话已过期，请重新登录');
      router.replace('/login');
    }
  } else {
    console.log('[Layout] 用户已登录:', userStore.user?.username);
  }
});

const handleCommand = (command) => {
  if (command === 'logout') {
    ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    }).then(async () => {
      await userStore.logout();
      router.push('/login');
    }).catch(() => {});
  } else if (command === 'settings') {
    router.push('/settings/account');
  }
};
</script>

<style scoped>
.app-layout {
  height: 100vh;
}

.fixed-aside {
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  z-index: 1000;
}

.sidebar {
  height: 100vh;
  background-color: #3D6E59;
  overflow-x: hidden;
  position: fixed;
  width: 200px;
  z-index: 1000;
  left: 0;
  top: 0;
}

.logo {
  height: 60px;
  display: flex;
  justify-content: center;
  align-items: center;
  color: white;
}

.logo h2 {
  margin: 0;
  color: #9BFFDA;
  font-size: 20px;
  text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.2);
}

.sidebar-menu {
  border-right: none;
}

.sidebar-menu :deep(.el-sub-menu__title:hover) {
  background-color: #4E8C71 !important;
}

.sidebar-menu :deep(.el-menu-item:hover) {
  background-color: #4E8C71 !important;
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  background-color: #2A4D3E !important;
}

.main-container {
  display: flex;
  flex-direction: column;
  margin-left: 200px; /* 与侧边栏宽度相同 */
  width: calc(100% - 200px);
}

.el-header {
  background-color: #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
  padding: 0 20px;
  display: flex;
  align-items: center;
  border-bottom: 2px solid #C6F7E2;
}

.header-content {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.username {
  font-size: 14px;
  color: #3D6E59;
}

.el-main {
  background-color: #E3F2ED;
  padding: 20px;
}

:deep(.el-avatar) {
  background-color: #2A4D3E;
}
</style> 