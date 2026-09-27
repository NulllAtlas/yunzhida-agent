# backend · RoadMind 后端

FastAPI + LangGraph 多智能体链路。

## 目录

```
backend/
├── app/
│   ├── main.py            # FastAPI 入口
│   ├── config.py          # 环境配置
│   ├── store.py           # 内存任务存储 + 图调用
│   ├── schemas/           # scene/judgment/response 数据契约
│   ├── routers/           # upload/task/result/auth/cases/ws
│   ├── services/          # llm / rag / judge / respond / mock_data
│   └── graph/             # LangGraph 节点与 builder（perceive→judge→respond→aggregate）
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## 本地运行（骨架 / mock 阶段）

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

访问文档：http://localhost:8000/docs

## 链路说明

- `POST /api/v1/upload` 上传视频 → 创建任务 → 后台 `run_task` 走图。
- 当前感知节点返回 **mock scene**（追尾示例），判定/应急为规则实现。
- 状态查询 `GET /api/v1/task/{id}`，结果 `GET /api/v1/result/{id}`。

## 待接入（按分工）

- **D3**：`services/rag.py` 接 chromadb + embedding。
- **D3**：`services/llm.py` 接 MoMA 网关（鉴权/超时/重试）。
- **D4**：`services/judge.py` 接真 LLM。
- **D6**：移除 mock，perceive 调 P3 服务。
