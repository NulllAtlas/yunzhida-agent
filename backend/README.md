# backend · 云智达 后端

FastAPI + LangGraph 多智能体链路（P2 · D1–D11 完成态）。

## 目录

```
backend/
├── app/
│   ├── main.py              # FastAPI 入口（路由装配 / 异常处理 / 静态前端挂载）
│   ├── core/                # config / db(SQLite) / security(JWT) / errors / logging
│   ├── schemas/models.py    # scene/judgment/response 数据模型
│   ├── graph/               # LangGraph：perceive→retrieve→judge→respond→aggregate
│   │   └── nodes/           # 各智能体节点
│   ├── services/            # perception(M1) / frames(视频分帧) / rag(M2) / llm(M3+M4)
│   └── api/                 # 路由：auth / cases / tasks(任务管理) / police / progress(WS)
├── scripts/index_rules.py   # chromadb 法条/案例入库脚本
├── tests/                   # pytest 用例
├── requirements.txt
└── run_dev.bat
```

## 本地运行（默认 mock，无需任何凭据）

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate     # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

或直接运行 `run_dev.bat`。打开 <http://localhost:8000/docs> 调接口，
<http://localhost:8000> 查看打包后的双视角界面。

## 接口

见 `docs/roadmind/API.md`：

- `POST /api/auth/register` / `POST /api/auth/login` —— 注册 / 登录（JWT，owner/police）
- `POST /api/cases` —— 创建案件并启动多智能体分析
- `GET /api/tasks/{id}/status` / `GET /api/tasks/{id}/result` —— 状态 / 结果
- `WS /api/ws/tasks/{id}` —— 阶段进度实时推送
- `GET /api/cases` / `GET /api/cases/{id}` / `GET /api/cases/{id}/draft` —— 交警端（需 police 角色）
- `GET /api/metrics` / `GET /health` —— 运维

## 测试

```bash
cd backend
pytest            # 51 项：主链路 / 鉴权 / WebSocket / RAG 回归 / bugfix 回归
```

`tests/test_bugfix_regressions.py` 逐条锁住已修复缺陷，含两个**正向对照**
（真实追尾必须穿过过检过滤并让门控放行、规则兜底必须给出事故类型）——
没有对照就无法证明收紧阈值之后真事故还能被检出。

## 设计说明

- **功能不砍、精度递进**：默认 `use_mock=True`，全链路可跑可演示；配置 `.env` 后
  判定/应急节点自动接真实 MoMA 网关，失败回退规则匹配，接口永不因模型抖动 500。
- **多智能体交互**：LangGraph 状态图编排 感知 → 检索 → 判定 → 应急 → 汇聚，
  逐节点消费状态流以实时推送阶段进度。
- **判定定位辅助建议**：`judgment.note` 明确"非最终裁定"。
- **并发与熔断**：信号量限流 `MAX_CONCURRENCY`（默认 4），单任务超时 `TASK_TIMEOUT_S`
  自动熔断；任务完成后结果落 SQLite，供交警端案件列表/详情/草稿使用。

## 部署

```bash
docker compose up --build     # 仓库根目录执行
```

运维手册（换模型 / 加规则 / 排障）：`deploy/docs/RUNBOOK.md`。