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

## 2.1 统一提交入口（视频 / 文字 / 现场照片）

`POST /api/submissions` — **202**（`multipart/form-data`）

前端（车主端与交警端共用的提交表单）实际走的就是这个入口。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `description` | text，可选 | 用户补充的文字描述，进判定上下文的「事故描述」 |
| `video` | file，可选 | 行车记录仪视频（mp4/mov/avi/mkv，≤ `max_upload_mb`） |
| `photos` | file[]，可选 | 现场照片，**同名 key 多次传**；≤3 张、每张 ≤10MB、仅 `image/*` |

- 三者**任意组合**、至少给一个：全空返回 `EMPTY_INPUT`（422）；
  照片超限 `TOO_MANY_PHOTOS`，类型/体积不符 `INVALID_FILE` / `FILE_TOO_LARGE`。
- **文字与场景证据是两份独立输入，合并后同时进判定** —— 不再是有视频就把文字丢掉。
- 照片走单帧检测（`app/algo/photo_detector.py`），证据落在 `result.scene.photos`
  （字段见 SCENE-SCHEMA v4）；照片是静态证据，**不参与事故门控**。
- 返回结构与 `POST /api/cases` 相同（TaskInfo）。

```json
{ "task_id": "adf72a071510", "status": "pending", "progress": 0.0 }
```

> `POST /api/videos`（仅视频）与 `POST /api/cases`（JSON，文字/已有媒体）保留不变，
> 分别供简单上传与带 `video_id` 的调用方使用。

## 3. 任务状态查询（D2）

`GET /api/tasks/{task_id}/status`

- 状态流转：`pending → perceiving → retrieving → judging → responding → done | failed`
- 阶段进度：0.0 → 0.2 → 0.4 → 0.6 → 0.8 → 1.0

```json
{ "task_id": "adf72a071510", "status": "done", "progress": 1.0, "result": { "..." } }
```

## 3.1 研判记录（车主端记录列表 / 跨设备）

`GET /api/history?limit=20&offset=0`

- 记录落在后端 SQLite（创建与完成时各写一次），**换浏览器、换设备看到的是同一份**，
  前端不再依赖 localStorage。
- 不鉴权：`POST /api/videos` 本身就允许匿名提交，车主端也没有账号概念；
  等记录要按账号归属时再加 owner 过滤。
- `status` 非终态但后端内存里已无该任务（进程重启留下的半截任务）→ 返回
  `failed` + `error`「后端重启，该次分析已中断」，避免前端一直转圈。
- 列表项**带完整 `result`**（车主端直接渲染历史结论，不必逐条再查详情）。

```json
{ "code": 0, "msg": "ok", "data": [
  {
    "task_id": "adf72a071510",
    "filename": "行车记录仪.mp4",
    "input_text": "对方压实线变道",
    "photos": ["adf72a071510_p0.jpg"],
    "status": "done",
    "accident_type": "追尾",
    "error": null,
    "created_at": "2026-10-06T02:06:29+00:00",
    "updated_at": "2026-10-06T02:06:35+00:00",
    "result": { "...": "scene / judgment / response 结构同 §4" }
  }
] }
```

> `filename` 只在本次提交带了视频时非空（纯照片/文字提交为空串）；`photos` 是落盘的存储名，
> 仅用于显示"交了几张"，原图不回显。

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
- **P4 联调占位**：`POST /api/upload`（图片）、`POST /api/audit`（审核）是前端早期联调的**固定返回**，
  不进链路。已无前端调用方（提交入口统一走 §2.1 的 `POST /api/submissions`）；
  保留是为了不破坏旧联调脚本与 `views/PoliceDetail.vue` 的调用。