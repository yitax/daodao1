import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '../store/user'

// 路由懒加载
const Login = () => import('../views/Login.vue')
const Register = () => import('../views/Register.vue')
const Layout = () => import('../views/Layout.vue')
const Chat = () => import('../views/Chat.vue')
const Reports = () => import('../views/Reports.vue')
const Summary = () => import('../views/reports/Summary.vue')
const DailyTrend = () => import('../views/reports/DailyTrend.vue')
const CategoryRanking = () => import('../views/reports/CategoryRanking.vue')
const TransactionRanking = () => import('../views/reports/TransactionRanking.vue')
const Ledger = () => import('../views/reports/Ledger.vue')
const SpendingHabits = () => import('../views/reports/SpendingHabits.vue')
const Settings = () => import('../views/Settings.vue')
const PersonalitySettings = () => import('../views/settings/PersonalitySettings.vue')
const AccountSettings = () => import('../views/settings/AccountSettings.vue')
const ManualEntry = () => import('../views/ManualEntry.vue')
const BatchImport = () => import('../views/BatchImport.vue')
const routes = [
    {
        path: '/',
        name: 'layout',
        component: Layout,
        redirect: '/chat',
        meta: { requiresAuth: true },
        children: [
            {
                path: 'chat',
                name: 'chat',
                component: Chat,
                meta: { title: '聊天记账' }
            },
            {
                path: 'manual',
                name: 'manual',
                component: ManualEntry,
                meta: { title: '手动记账' }
            },
            {
                path: 'batch',
                name: 'batch',
                component: BatchImport,
                meta: { title: '批量导入' }
            },
            {
                path: 'reports',
                name: 'reports',
                component: Reports,
                redirect: '/reports/summary',
                meta: { title: '财务报表' },
                children: [
                    {
                        path: 'summary',
                        name: 'summary',
                        component: Summary,
                        meta: { title: '收支总览' }
                    },
                    {
                        path: 'daily',
                        name: 'daily',
                        component: DailyTrend,
                        meta: { title: '每日收支趋势' }
                    },
                    {
                        path: 'category',
                        name: 'category',
                        component: CategoryRanking,
                        meta: { title: '分类排行' }
                    },
                    {
                        path: 'ranking',
                        name: 'ranking',
                        component: TransactionRanking,
                        meta: { title: '明细排行' }
                    },
                    {
                        path: 'ledger',
                        name: 'ledger',
                        component: Ledger,
                        meta: { title: '每日报表' }
                    }
                ]
            },
            {
                path: 'spending-habits',
                name: 'spending-habits',
                component: SpendingHabits,
                meta: { title: '消费习惯分析' }
            },
            {
                path: 'settings',
                name: 'settings',
                component: Settings,
                redirect: '/settings/personality',
                meta: { title: '设置' },
                children: [
                    {
                        path: 'personality',
                        name: 'personality',
                        component: PersonalitySettings,
                        meta: { title: 'AI个性设置' }
                    },
                    {
                        path: 'account',
                        name: 'account',
                        component: AccountSettings,
                        meta: { title: '账户设置' }
                    }
                ]
            }
        ]
    },
    {
        path: '/login',
        name: 'login',
        component: Login,
        meta: { title: '登录' }
    },
    {
        path: '/register',
        name: 'register',
        component: Register,
        meta: { title: '注册' }
    },
    {
        path: '/:pathMatch(.*)*',
        redirect: '/'
    }
]

const router = createRouter({
    history: createWebHistory(),
    routes
})

// 全局前置守卫
router.beforeEach(async (to, from, next) => {
    // 设置页面标题
    document.title = to.meta.title ? `${to.meta.title} - 叨叨记账` : '叨叨记账'

    const userStore = useUserStore()
    console.log(`[Router] 路由跳转: ${from.path} -> ${to.path}, 认证状态: ${userStore.isLoggedIn ? '已登录' : '未登录'}`)

    // 检查路由是否需要身份验证
    if (to.matched.some(record => record.meta.requiresAuth)) {
        // 检查是否有token但未登录
        const sessionToken = sessionStorage.getItem('token');
        const localToken = localStorage.getItem('token');
        const hasToken = !!localToken || !!sessionToken;

        // 确保token在两个存储位置都同步
        if (sessionToken && !localToken && localStorage.getItem('rememberMe') === 'true') {
            localStorage.setItem('token', sessionToken);
        } else if (localToken && !sessionToken) {
            sessionStorage.setItem('token', localToken);
        }

        if (hasToken && !userStore.isLoggedIn) {
            console.log('[Router] 发现token但用户未登录，尝试恢复会话...');
            try {
                // 尝试使用token恢复会话
                const user = await userStore.checkAuth();
                if (!user) {
                    console.log('[Router] 恢复会话失败，重定向到登录页面');
                    return next({ name: 'login', query: { redirect: to.fullPath } });
                }
                console.log('[Router] 会话恢复成功，继续导航');
                return next();
            } catch (error) {
                console.error('[Router] 恢复会话出错:', error);
                return next({ name: 'login', query: { redirect: to.fullPath } });
            }
        }
        // 如果用户未登录，重定向到登录页面
        else if (!userStore.isLoggedIn) {
            console.log('[Router] 用户未登录，重定向到登录页面');
            return next({ name: 'login', query: { redirect: to.fullPath } });
        }

        console.log('[Router] 用户已登录，允许访问');
        return next();
    }

    // 如果已登录，访问登录/注册页面时重定向到首页
    if ((to.name === 'login' || to.name === 'register') && userStore.isLoggedIn) {
        return next({ name: 'chat' });
    }

    next();
})

export default router 