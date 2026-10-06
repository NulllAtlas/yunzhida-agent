import { createRouter, createWebHashHistory } from 'vue-router'
import { getUser } from '../api/auth'

/** 路由级鉴权声明（放在 meta 里，由下面的守卫统一消费）。 */
interface RouteAuthMeta {
  requiresAuth?: boolean
}

/**
 * 未登录时回入口页并把登录弹窗叫起来。
 * 登录是 Home 上的一个弹窗，不是独立页面，所以这里用 query 传递意图而不是路由。
 */
function requireLogin(to: string) {
  return { path: '/', query: { login: '1', redirect: to } }
}

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    // 入口选择页，也是登录后的落脚点；登录弹窗就挂在这一页上
    { path: '/', component: () => import('../views/Home.vue') },
    // 旧的 /login 页面已并入首页弹窗，保留跳转兼容旧链接
    { path: '/login', redirect: (to) => ({ path: '/', query: { login: '1', ...to.query } }) },
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
