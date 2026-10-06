# frontend · 云智达 前端（Vue 3 + TypeScript + Vite）

车主端 / 交警端双视角界面，一个 SPA，路由见 `src/router/index.ts`。

## 怎么跑

前端**不跑独立 dev server**，只负责构建；产物由后端在 **http://localhost:8000** 托管。

```bash
cd frontend
npm install
npm run build          # 产出 dist/
cd ../backend
run_dev.bat            # 或 uvicorn app.main:app --reload --port 8000
```

然后浏览器打开 <http://localhost:8000>：接口（`/api/*`、`/health`）和页面同源，
登录态直接落在同一个 origin 的 localStorage 上，不需要任何跨端口交接。

改了前端代码 → 重新 `npm run build`，刷新页面即可。

## 目录

```
src/
├── api/         # 后端接口封装（auth 会话 / cases 案件 / 其余走 fetch）
├── components/  # 通用组件（登录弹窗、进度条、结果卡片、上传区）
├── router/      # 路由与登录守卫
├── types/       # 前后端契约类型
└── views/       # Home 入口页 / Owner 车主端 / Police 交警端 / PoliceDetail 认定详情
```

容器部署见仓库根 `docker-compose.yml`（前端静态走 nginx 的 8080）。
