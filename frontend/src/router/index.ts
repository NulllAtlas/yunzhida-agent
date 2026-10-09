import { createRouter, createWebHashHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    // 首页：云智达品牌展示 + 系统状态；登录/注册从首页导航到 /login 进行
    { path: '/', component: () => import('../views/Home.vue') },
    // 全屏登录 / 注册页（独立路由、整屏布局，带"返回首页"按键；
    // 已登录访问会被 Login.vue 直接带到 :8000 的研判界面）
    { path: '/login', component: () => import('../views/Login.vue') },
    // 其余路径一律回落首页
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
