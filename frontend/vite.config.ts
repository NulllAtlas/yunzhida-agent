import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 本地开发：dev server 跑在 8080（与 docker 部署的 nginx 端口一致），
// /api 与 /outputs 代理到后端 :8000；npm run build 时用不到这些配置，
// 产物 dist 仍由后端在 :8000 托管（backend/app/main.py）。
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 8080,
    proxy: {
      '/api': 'http://localhost:8000',
      '/outputs': 'http://localhost:8000',
      // Home.vue 的系统状态调 /health（不带 /api 前缀），同样代理到后端
      '/health': 'http://localhost:8000',
    },
  },
})
