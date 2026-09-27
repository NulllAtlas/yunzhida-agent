# backend · RoadMind 后端

FastAPI + LangGraph 多智能体链路（组员骨架版）。

## 目录

```
backend/
├── app/
│   ├── main.py              # FastAPI 入口（含静态前端挂载）
│   ├── core/config.py       # 配置（use_mock 开关 / MoMA / chroma）
│   ├── schemas/models.py    # scene/judgment/response 数据模型
│   ├── graph/               # LangGraph：perceive→retrieve→judge→respond→aggregate
│   │   └── nodes/           # 各智能体节点
│   ├── services/            # perception(M1) / rag(M2) / llm(M3+M4)
│   └── api/                 # 路由（cases） + 任务管理（tasks）
├── requirements.txt
└── run_dev.bat
```

## 本地运行（MVP，默认 mock，无需任何凭据）

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

或直接运行 `run_dev.bat`。

打开 http://localhost:8000 即可使用双视角（车主/交警）界面。

## 接口

见 `docs/roadmind/API.md`：
- `POST /api/cases` 创建案件分析
- `GET /api/tasks/{id}/status` 状态
- `GET /api/tasks/{id}/result` 结果

## 设计说明

- **功能不砍、精度递进**：MVP 阶段 services 全部走 mock（`use_mock=True`），全链路可跑可演示；真实视频感知（YOLO）、LLM（MoMA 网关）、向量检索（chromadb）在迭代阶段替换（代码已标 `TODO(迭代)`）。
- **多智能体交互**：LangGraph 状态图编排 感知 → 检索 → 判定 → 应急 → 汇聚。
- **判定定位辅助建议**：`judgment.note` 明确"非最终裁定"。

## 待接入（按分工）

- **D3**：`services/rag.py` 接 chromadb 向量检索；`services/llm.py` 接 MoMA 网关。
- **D3**：`services/perception.py` 接入真实视频检测（YOLO）。
- **D6**：全链路真实数据，移除 mock 兜底。
