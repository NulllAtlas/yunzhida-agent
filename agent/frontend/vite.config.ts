import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 前端没有独立 dev server：只负责 build，产物 dist 由后端在 :8000 托管
// （backend/app/main.py 挂载 frontend/dist），改完前端跑一次 npm run build 即可。
export default defineConfig({
  plugins: [vue()],
})
