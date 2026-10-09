# API.md · 后端接口契约（Day1 起 P2 主导 / 持续维护）

> 版本：v0.4（2026-10-09，新增 B1–B4：自动取证 / 双端推送 / 车主回执 / 状态机扩展，与 `backend/app/**` 实现一致）
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
`TASK_NOT_FOUND`(404) / `CASE_NOT_FOUND`(404) / `NOT_DISPENSED`(422) /
`TASK_PROCESSING`(202) / `INTERNAL_ERROR`(500)。

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

## 2.2 行车记录仪自动取证入口（B1）

`POST /api/cases/forensics` — **202**（`multipart/form-data`）

事故发生时由**设备自动触发**（替代车主手动上传）：上传滚动录像 + 触发时刻，
后端按触发点回退 `pre_seconds` 秒截出"事发前画面"片段，只把这段证据送进研判链路。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `video` | file，**必填** | 行车记录仪滚动录像（mp4/mov/avi/mkv，≤ `max_upload_mb`） |
| `trigger_seconds` | number，可选 | 事故触发时刻（视频内秒数）；缺省视为"刚发生"，取录像末尾 |
| `pre_seconds` | number，可选 | 事发前回看秒数，默认 `30`（0–300） |
| `post_seconds` | number，可选 | 事后保留秒数，默认 `5`（0–300） |
| `device_id` | text，可选 | 设备编号，写入取证时间线便于溯源 |
| `description` / `photos` | 可选 | 同 §2.1，照片走单帧检测补充证据 |

- 起始业务状态为 `forensics`（自动取证中，见 §6.1）；研判完成后自动推进到 `pending_review`。
- 截取失败（视频不可解码等）**不报错**：降级为使用原视频继续研判，并在时间线说明原因。
- 取证过程写入案件时间线（`kind="forensics"`），车主端与交警端都能看到取了哪一段。
- 返回结构与 `POST /api/cases` 相同（TaskInfo）。

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
- 不强制鉴权，但支持**可选令牌归属过滤**（B2）：带 `Authorization: Bearer <JWT>` 且为
  `owner` 角色时只返回本人名下案件；交警或匿名（无令牌）返回全部记录 —— 与 `POST /api/submissions`
  允许匿名提交保持一致，同时满足车主端"只看自己的车"。
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

## 5.1 双端案件事件流（B2）

`WS /api/ws/notifications?token=<JWT>` — 全局案件事件流（与 §5 的**单任务**进度流不同）。

- 连接时用 query 参数 `token` 鉴权（浏览器 WebSocket 无法自定义 Header）；令牌缺失/无效
  按**匿名**处理：保持连接但不接收任何事件。
- 可见性：**交警**令牌收到全部案件；**车主**令牌只收 `owner_id` 与本人账号一致的事件；
  匿名不接收 —— 保证"案件与车主绑定"后互不串台。
- 案件**创建**（落库）与研判**完成/失败**时各推一次，供车主端与交警端**同时刷新**，无需轮询：

```json
{ "type": "case_created", "task_id": "adf72a071510", "owner_id": "driver01",
  "status": "pending", "flow_status": "forensics", "filename": "", "input_text": "" }
{ "type": "case_done",    "task_id": "adf72a071510", "owner_id": "driver01",
  "status": "done",    "flow_status": "pending_review", "result": { "...": "同 §4" } }
{ "type": "case_failed",  "task_id": "adf72a071510", "owner_id": "driver01",
  "status": "failed",  "flow_status": "pending_review", "error": "研判超时" }
```

> 进程内内存总线（`app/api/notifications.py` 的 `EventHub`），单机演示足够；
> 多实例部署需换成 Redis 之类的共享总线。

## 6. 交警端（D7，需 police 角色）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/cases?limit=20&offset=0` | 案件列表（摘要，按创建时间倒序） |
| GET | `/api/cases/{task_id}` | 案件详情（含完整 result） |
| GET | `/api/cases/{task_id}/draft` | 《道路交通事故认定书（草稿）》纯文本，带 `Content-Disposition` |
| GET | `/api/cases/{task_id}/interact` | 双端联动视图：`flow_status`/`flow_label` + 时间线 + `pending_ack`（待回执条数） |
| POST | `/api/cases/{task_id}/interact/ack` | 车主回执（B3）：标记下发内容已接收并推进 `dispensed → received`，幂等、**不鉴权** |
| POST | `/api/cases/{task_id}/police/message` | 交警下发消息 → 时间线 `kind="message"` |
| POST | `/api/cases/{task_id}/police/disposition` | 交警下发处理意见（处分）→ 时间线 `kind="disposition"`，状态推进到 `dispensed` |
| POST | `/api/cases/{task_id}/police/flow` | 交警推进流转：`accept→reviewing` / `approve→decided` / `reject→rejected` / `close→closed` |

> 读取类接口对任意登录用户开放（车主端要能看流转与下发内容），**写操作**仍限 police 角色（否则 403）。

## 6.1 双端联动与案件状态机（B2/B3/B4）

交警确认并向车主下发后，车主端通过 `GET .../interact` 看到时间线、通过 `POST .../ack` 回执：

```json
{ "code": 0, "msg": "ok",
  "data": { "acked": 1, "pending_ack": 0, "flow_status": "received", "flow_label": "车主已接收并回执" } }
```

- 状态未到 `dispensed`（交警尚未下发）时回执返回 **422** `NOT_DISPENSED`「交警尚未下发处理意见，暂无可回执内容」。
- 重复回执**不报错**、条数不再增加（前置条件检查 + 幂等 UPDATE，`acked` 第二次为 0）。

业务状态机 `flow_status`（与 §3 的分析状态 `status` 分离，二者各自演进）：

```
forensics（自动取证） → analyzing（AI 研判） → pending_review（待交警受理）
      → reviewing（审核中） → decided（责任已认定） → dispensed（已下发处理意见）
      → received（车主已接收并回执） → closed（已结案）
```

- 起始态：手动提交为 `submitted`，行车记录仪自动取证（§2.2）为 `forensics`；研判完成后
  统一收敛到 `pending_review`（`submitted` / `forensics` / `analyzing` 三态都会自动推进）。
- `rejected`（已驳回，待补充材料）为审核分支终态，可再流转回 `reviewing`。

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