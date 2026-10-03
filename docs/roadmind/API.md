# API.md · 后端接口契约（Day1 · P2 主导 / P1 确认）

> 版本：v0.2（2026-09-28，同步组员骨架）
> 语言：REST。Base URL：`http://localhost:8000`。
> MVP 阶段所有服务走 mock（`app/core/config.py` 中 `use_mock=True`），无需真实凭据即可跑通。

## 1. 创建案件并启动分析

`POST /api/cases`
- body（JSON）：

```json
{ "text_description": "路口我车直行，对方左转弯未让行发生碰撞" }
```

- 输入方式：`video_id` / `scene_id` / `text_description` 三选一（MVP 用文字描述驱动，前端/感知降级兜底）。
- 返回 `202` 任务信息：

```json
{ "task_id": "adf72a071510", "status": "pending", "progress": 0.0 }
```

## 2. 任务状态查询

`GET /api/tasks/{task_id}/status`
- 状态流转：`pending → perceiving → retrieving → judging → responding → done | failed`
- 返回：

```json
{ "task_id": "adf72a071510", "status": "done", "progress": 1.0, "result": { "..." } }
```

## 3. 任务结果查询

`GET /api/tasks/{task_id}/result`
- 完成（done/failed）时返回完整结果；处理中返回 `202`。

```json
{
  "task_id": "...",
  "status": "done",
  "result": {
    "case_id": "...",
    "scene": { "...": "见 SCENE-SCHEMA" },
    "retrieved": [ { "title": "道交法 第43条", "source": "law" } ],
    "judgment": { "responsibility": { "party_1": "primary", "party_2": "none", "split": "100/0" }, "basis": [], "reasoning": [], "confidence": 0.8 },
    "response": { "accident_type": "rear_end", "priority": 2, "steps": [], "insurance": "" }
  }
}
```

## 4. 其它

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/health` | 健康检查（返回 `use_mock`） |
| GET  | `/` | 前端单页（frontend/index.html） |
| GET  | `/static` | 静态资源 |

## 5. 状态码约定

| code | 含义 |
| --- | --- |
| 404 | 任务/案件不存在 |
| 202 | 任务仍在处理（result 未就绪） |

## 说明

- **契约结构**：`scene.json` / `judgment.json` / `response.json` 详细结构见 `SCENE-SCHEMA.md` 与 `CONTRACTS.md`（字段与 `app/schemas/models.py` 一致）。
- **降级链路**：感知置信低时由前端转文字补录，以 `text_description` 重新触发判定，保证任意输入都能出结果。
- **MoMA 网关（P2，D3）**：`app/services/llm.py` 封装统一 `call_chat()`（OpenAI 兼容网关，带鉴权/超时/重试）。`use_mock=True` 或未配置网关时走规则兜底；`use_mock=False` 且配置 `.env` 后走真实 MoMA。配置字段见 `.env.example`：`MOMA_API_KEY` / `MOMA_BASE_URL` / `MODEL_FAST` / `MODEL_STRONG`。
- **RAG 入库（P2，D3）**：`app/services/rag.py` 支持 chromadb 向量检索（轻量本地 n-gram embedding，离线可用），不可用时自动降级为关键词检索。法条/案例入库：
  ```bash
  cd backend
  python scripts/index_rules.py                       # 内置规则入库
  python scripts/index_rules.py --dir ../data/cases   # 从目录 .md 入库
  ```
