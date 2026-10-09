import { createRouter, createWebHashHistory } from 'vue-router'
import { getUser } from '../api/auth'

/** 路由级鉴权声明（放在 meta 里，由下面的守卫统一消费）。 */
interface RouteAuthMeta {
  requiresAuth?: boolean
}

/**
 * 未登录时跳到全屏登录页，并把想去的地方带在 query 里，登录成功后再跳回去。
 */
function requireLogin(to: string) {
  return { path: '/login', query: { redirect: to } }
}

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    // 入口选择页：已登录时展示两个端的入口与系统状态
    { path: '/', component: () => import('../views/Home.vue') },
    // 全屏登录 / 注册页（独立路由、整屏布局）
    { path: '/login', component: () => import('../views/Login.vue') },
    // 两个端都只要求“已登录”。身份由入口页选择，不再由账号角色决定，
    // 所以这里不设 role 限制——车主账号也能进交警端看看。
    { path: '/owner', component: () => import('../views/Owner.vue'), meta: { requiresAuth: true } },
    { path: '/police', component: () => import('../views/Police.vue'), meta: { requiresAuth: true } },
    {
      path: '/police/detail/:id',
      name: 'police-detail',
      component: () => import('../views/PoliceDetail.vue'),
      meta: { requiresAuth: true },
    },
  ],
})

router.beforeEach((to) => {
  const meta = to.meta as RouteAuthMeta
  if (!meta.requiresAuth) return true
  if (!getUser()) return requireLogin(to.fullPath)
  return true
})
