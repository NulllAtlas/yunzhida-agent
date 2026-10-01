import { createRouter, createWebHashHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/login' },
    { path: '/login', component: () => import('../views/Login.vue') },
    { path: '/owner', component: () => import('../views/Owner.vue') },
    { path: '/police', component: () => import('../views/Police.vue') },
    { path: '/police/detail/:id', name: 'police-detail', component: () => import('../views/PoliceDetail.vue') },
  ],
})