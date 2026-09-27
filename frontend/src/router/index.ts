import { createRouter, createWebHistory } from 'vue-router'
import OwnerView from '../views/OwnerView.vue'
import PoliceView from '../views/PoliceView.vue'
import LoginView from '../views/LoginView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/owner' },
    { path: '/owner', name: 'owner', component: OwnerView },
    { path: '/police', name: 'police', component: PoliceView },
    { path: '/login', name: 'login', component: LoginView },
  ],
})
