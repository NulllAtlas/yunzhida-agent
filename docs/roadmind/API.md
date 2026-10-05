# API.md · 后端接口契约（Day1 起 P2 主导 / 持续维护）

> 版本：v0.3（2026-10-05，D1–D11 完成态，与 `backend/app/**` 实现一致）
> 语言：REST + WebSocket。Base URL：`http://localhost:8000`。
> 全链路默认走 mock（`use_mock=True`），无需真实凭据即可跑通；配置 `.env` 后自动接真实 MoMA 网关。

## 0. 统一响应结构

成功：

```json
{ "code": 0, "msg": "ok", "data": { } }
```

失败（HTTP 状态码同时有效）：

```json
{ "code": "TASK_NOT_FOUND", "msg": "任务不存在", "data": null }
```

错误码：`VALIDATION_ERROR`(422) / `EMPTY_INPUT`(422) / `USER_EXISTS`(409) /
`BAD_CREDENTIALS`(401) / `UNAUTHORIZED`(401) / `FORBIDDEN`(403) /
`TASK_NOT_FOUND`(404) / `CASE_NOT_FOUND`(404) / `TASK_PROCESSING`(202) / `INTERNAL_ERROR`(500)。

## 1. 鉴权（D7）

### `POST /api/auth/register`

```json
{ "username": "officer01", "password": "secret123", "role": "police" }
```

- `role`：`owner`（车主，默认） / `police`（交警）。
- 返回 `201`：`{"code":0,"msg":"ok","data":{"username":"officer01","role":"police"}}`

### `POST /api/auth/login`

```json
{ "username": "officer01", "password": "secret123" }
```

```json
{ "code": 0, "msg": "ok",
  "data": { "access_token": "<JWT>", "token_type": "bearer", "role": "police", "expires_in": 43200 } }
```

后续请求带 `Authorization: Bearer <access_token>`。

## 2. 创建案件并启动分析（D1/D2）

`POST /api/cases` — **202**

```json
{ "text_description": "路口我车直行，对方左转弯未让行发生碰撞" }
```

- 输入三选一：`video_id` / `scene_id` / `text_description`（全空返回 `EMPTY_INPUT`）。
- 返回任务信息：

```json
{ "task_id": "adf72a071510", "status": "pending", "progress": 0.0 }
```

## 3. 任务状态查询（D2）

`GET /api/tasks/{task_id}/status`

- 状态流转：`pending → perceiving → retrieving → judging → responding → done | failed`
- 阶段进度：0.0 → 0.2 → 0.4 → 0.6 → 0.8 → 1.0

```json
{ "task_id": "adf72a071510", "status": "done", "progress": 1.0, "result": { "..." } }
```

## 4. 任务结果查询（D2）

`GET /api/tasks/{task_id}/result`

- 完成（`done`/`failed`）返回完整结果；处理中返回 **202** `TASK_PROCESSING`。

```json
{
  "task_id": "...",
  "status": "done",
  "result": {
    "case_id": "...",
    "scene": { "...": "见 SCENE-SCHEMA" },
    "retrieved": [ { "id": "law-043", "title": "道交法 第43条", "source": "law", "score": 1.0 } ],
    "judgment": {
      "responsibility": { "party_1": "primary", "party_2": "none", "split": "100/0" },
      "basis": [], "reasoning": [], "confidence": 0.8,
      "note": "本结果为智能辅助研判建议，非最终裁定，请以交管部门认定为准。"
    },
    "response": { "accident_type": "rear_end", "priority": 2, "steps": [], "insurance": "" }
  }
}
```

## 5. 进度推送（D4/D5）

`WS /api/ws/tasks/{task_id}`

> **路径定型说明**：D1 排期草稿（`TEAM-WORKFLOW.md`）中该接口写作 `WS /progress`，
> 正式契约定型为 `/api/ws/tasks/{task_id}` —— 与 REST 的 `/api/tasks/{id}/status`
> 保持同一资源层级，便于 Nginx 按 `/api/` 统一反代。以本文档为准。

连接后依次收到：

```json
{ "type": "status",   "status": "perceiving", "progress": 0.2, "step": "perceiving" }
{ "type": "progress", "status": "judging",    "progress": 0.6, "step": "judging" }
{ "type": "done",     "status": "done",       "progress": 1.0, "result": { "..." } }
```

- 任务不存在时推送 `{"type":"error","status":"not_found"}` 并以 `4404` 关闭。
- 失败任务推送 `{"type":"failed","error":"..."}`。

## 6. 交警端（D7，需 police 角色）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/cases?limit=20&offset=0` | 案件列表（摘要，按创建时间倒序） |
| GET | `/api/cases/{task_id}` | 案件详情（含完整 result） |
| GET | `/api/cases/{task_id}/draft` | 《道路交通事故认定书（草稿）》纯文本，带 `Content-Disposition` |

## 7. 运维（D8）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/metrics` | 任务计数（created/running/done/failed）与并发水位 |
| GET | `/health` | 健康检查：`use_mock` / `rag_backend` / `llm_configured` / `max_concurrency` |
| GET | `/` | 前端单页（frontend/dist 存在时） |
| GET | `/docs` | OpenAPI 交互文档 |

并发与熔断：同一时刻最多 `MAX_CONCURRENCY`（默认 4）个任务执行，超出排队；
单任务超过 `TASK_TIMEOUT_S`（默认 180s）自动置 `failed` 熔断。

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
- **P4 联调占位**：`POST /api/upload`、`POST /api/audit` 为前端早期联调的固定返回，保留以免破坏
  `frontend/src/components/UploadZone.vue` 与 `views/PoliceDetail.vue`；真实链路请走上面的
  `POST /api/cases` → `GET /api/tasks/{id}/result`。