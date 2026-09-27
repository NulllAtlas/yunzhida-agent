# API.md · 后端接口契约（Day1 · P2 主导 / P1 确认）

> 版本：v0.1（2026-09-27）
> 语言：REST + WebSocket。Base URL：`/api/v1`。
> 所有接口已 mock 并联，谁都不等谁。

## 通用约定

- 统一错误码结构：`{ "code": 40001, "message": "...", "detail": "..." }`
- 认证：`Authorization: Bearer <JWT>`（D7 起），车主/交警角色区分。
- 时间：ISO 8601 UTC。

## 1. 文件上传

`POST /api/v1/upload`
- multipart/form-data，字段 `file`（视频 mp4/webm/avi），可选 `role`、`scene_note`。
- 返回：`202` 创建任务

```json
{ "task_id": "t_9f3c2", "status": "pending" }
```

## 2. 任务状态查询

`GET /api/v1/task/{task_id}`
- 返回状态流转：`pending → processing → done | failed`

```json
{
  "task_id": "t_9f3c2",
  "status": "processing",
  "stage": "judge",
  "progress": 0.65,
  "created_at": "2026-09-27T08:00:00Z"
}
```

## 3. 进度推送（WebSocket）

`WS /api/v1/ws/progress?task_id=t_9f3c2`
- 服务端推送阶段消息：`upload → perceive → retrieve → judge → respond → done`

```json
{ "type": "stage", "task_id": "t_9f3c2", "stage": "judge", "progress": 0.65 }
```

## 4. 结果查询

`GET /api/v1/result/{task_id}`
- 返回结果对象，含 `scene / judgment / response`（结构见数据契约）。

```json
{
  "task_id": "t_9f3c2",
  "scene": { "...": "见 SCENE-SCHEMA.md" },
  "judgment": { "...": "见 judgment 契约" },
  "response": { "...": "见 response 契约" },
  "created_at": "..."
}
```

## 5. 认证（D7 起）

- `POST /api/v1/register`：`{ username, password, role: "owner"|"police" }`
- `POST /api/v1/login`：`{ username, password }` → `{ token, role }`

## 6. 交警端

- `GET /api/v1/cases`：案件列表（当前用户可见）。
- `GET /api/v1/case/{id}`：案件详情（scene/judgment/response 全量）。
- `GET /api/v1/case/{id}/keyframes`：关键帧（P3）。
- `GET /api/v1/case/{id}/export`：认定书草稿导出。

## 7. 感知服务（P2 调 P3，内部）

- `POST /api/v1/perceive`：视频 → scene.json。
- `GET /api/v1/perceive/{id}/keyframes`：关键帧图。

## 8. 错误码表（初版）

| code | 含义 |
| --- | --- |
| 40000 | 参数错误 |
| 40001 | 未认证 |
| 40003 | 无权限 |
| 40400 | 任务/案件不存在 |
| 50000 | 内部错误 |
| 50001 | 视频解析失败 |
| 50002 | LLM 超时 |
| 50003 | 场景为空 |
