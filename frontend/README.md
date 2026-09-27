# frontend · RoadMind 前端

Vue3 + Vite + TS 双端应用（车主端 / 交警端）。

## 目录

```
frontend/
├── src/
│   ├── main.ts
│   ├── App.vue
│   ├── router/index.ts        # /owner /police /login
│   ├── views/                 # OwnerView / PoliceView / LoginView
│   ├── components/            # （待补充：上传、进度、结果卡片、可视化）
│   ├── types/index.ts         # 由 API 契约生成的 TS 类型
│   └── mock/index.ts          # mock 数据（联调前渲染用）
├── index.html
├── vite.config.ts             # /api 代理到 :8000
└── package.json
```

## 本地运行

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173（自动代理 `/api` 到后端 :8000）。

## 联调进度

- [ ] D4 车主端接真实 API（上传 → 轮询 → 结果）
- [ ] D7 交警端完整 + 角色权限
- [ ] D6 视频可视化组件（读 scene 轨迹/关键帧）
