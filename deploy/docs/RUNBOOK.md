# RUNBOOK · RoadMind 后端运行手册（P2 · D10）

> 适用版本：backend v0.2.0（D1–D11 完成态）
> 目标：任何人拿到仓库后，能在 5 分钟内把服务跑起来、换模型、加规则、排障。

---

## 1. 环境要求

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.12 | 后端 |
| Node.js | 20+ | 前端构建（可选） |
| Docker | 24+ | 容器化部署（可选） |

---

## 2. 本地启动（开发）

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # 不填也能跑（USE_MOCK=true）
uvicorn app.main:app --reload --port 8000
```

验证：

```bash
curl http://localhost:8000/health
# {"status":"ok","use_mock":true,"rag_backend":"keyword",...}
```

打开 <http://localhost:8000/docs> 可直接调接口。

> `rag_backend` 为 `keyword` 表示 chromadb 未生效（多为 onnxruntime 缺失），
> 服务仍可正常工作，仅检索退化为关键词匹配。

---

## 3. 容器化启动（演示 / 部署）

```bash
docker compose up --build
```

- 前端：<http://localhost:8080>
- 后端：<http://localhost:8000/docs>

`docker-compose.yml` 中 api 服务挂载命名卷 `roadmind-data`，
持久化向量库、上传文件与 SQLite 案件库；`web` 服务用 Nginx 托管前端并把
`/api/`（含 `/api/ws/` WebSocket）反代到 api 容器。

---

## 4. 换模型（接入真实 MoMA 网关）

1. 编辑 `backend/.env`：

   ```ini
   USE_MOCK=false
   MOMA_API_KEY=<团队 Token>
   MOMA_BASE_URL=<MoMA 统一网关地址>
   MODEL_FAST=<便宜模型 ID>
   MODEL_STRONG=<强模型 ID>
   ```

2. 重启服务，`GET /health` 应返回 `"use_mock": false, "llm_configured": true`。

- 判定节点使用 `MODEL_STRONG`；网关/鉴权/解析任何一步失败都会**自动回退到规则匹配**，
  不会因为模型抖动导致接口 500。
- 超时与重试：`LLM_TIMEOUT_S`（默认 60s）、`LLM_MAX_RETRIES`（默认 2）。
- 容器部署时通过环境变量注入（见 `docker-compose.yml` 的 `api.environment`）。

---

## 5. 加规则 / 加案例（RAG 入库）

```bash
cd backend
python scripts/index_rules.py                        # 用内置法条规则库入库
python scripts/index_rules.py --dir ../data/cases    # 把 data/cases/*.md 解析入库
```

- `.md` 支持两种写法：`# 标题 + 正文`（一条），或按 `## 二级标题` 切分成多条。
- 重复 id 会**覆盖**，不会产生重复条目。
- embedding 为本地 n-gram 哈希（blake2b 定盐），同一文本在任何机器上向量一致，
  无需下载模型、可离线运行。
- 新增静态法条请直接改 `app/services/rag.py` 的 `_LAW_POOL`。

---

## 6. 接口速查

| 方法 | 路径 | 说明 | 鉴权 |
| --- | --- | --- | --- |
| POST | `/api/auth/register` | 注册（owner / police） | - |
| POST | `/api/auth/login` | 登录换取 JWT | - |
| POST | `/api/cases` | 创建案件，启动多智能体链路（202） | - |
| GET | `/api/tasks/{id}/status` | 任务状态与进度 | - |
| GET | `/api/tasks/{id}/result` | 任务结果（处理中返回 202） | - |
| WS | `/api/ws/tasks/{id}` | 阶段进度实时推送 | - |
| GET | `/api/cases` | 案件列表（交警） | police |
| GET | `/api/cases/{id}` | 案件详情（交警） | police |
| GET | `/api/cases/{id}/draft` | 认定书草稿导出（交警） | police |
| GET | `/api/metrics` | 任务计数 / 并发水位 | - |
| GET | `/health` | 健康检查 | - |

统一响应结构：成功 `{"code":0,"msg":"ok","data":...}`，失败 `{"code":"<ERR_CODE>","msg":"...","data":null}`。

---

## 7. 常见问题

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 启动报 `Form data requires "python-multipart"` | 依赖未装 | `pip install -r requirements.txt` |
| `rag_backend` 一直是 `keyword` | onnxruntime 缺失/损坏 | 重装 `onnxruntime==1.20.1`；不影响主流程 |
| 任务 `failed`，错误含"任务超时" | 单任务超过 `TASK_TIMEOUT_S` | 调大 `TASK_TIMEOUT_S` 或检查 LLM 网关 |
| 任务一直 `processing` | LLM 网关不通且未回退 | 正常应回退规则；检查日志 `roadmind.access` |
| 401 / 403 | 未带 Token 或角色不符 | 先 `POST /api/auth/login`，交警接口需 police 角色 |
| 案件列表为空 | 案件只在任务完成后落库 | 等任务 `done` 后再查 |
| 视频案件 `scene.source` 仍是 `text` | 视频不在 `UPLOAD_DIR` 下或无法解码 | 确认 `video_id` 指向 `data/uploads` 中真实文件 |
| 抽帧太少 / 太慢 | 受分帧上限约束 | 调 `VIDEO_MAX_FRAMES` / `FRAME_MAX_WIDTH` / `VIDEO_EXTRACT_TIMEOUT_S` |

**视频分帧参数（D8 大视频策略）**：大视频不逐帧解码，按 `VIDEO_MAX_FRAMES` 均匀抽样，
用 `CAP_PROP_POS_MSEC` 直接定位采样点，长边缩放到 `FRAME_MAX_WIDTH`；超过
`VIDEO_MAX_DURATION_S` 只采样并标记 `truncated`，抽帧总耗时超过 `VIDEO_EXTRACT_TIMEOUT_S`
即熔断；任何失败都回落文字降级、不影响任务成功。关键帧落盘在
`FRAMES_DIR/{task_id}/`，中间帧路径写入 `scene.events[*].keyframe`。

日志：`logging` 统一格式，请求日志带耗时；响应头 `X-Process-Time-ms` 可直接观测单请求耗时。

---

## 8. 交付核对（D11）

- [x] 源码：`backend/app/**`（鉴权 / 任务管理 / 多智能体链路 / 路由）
- [x] 依赖：`backend/requirements.txt` 固定版本
- [x] 数据：`data/cases/*.md` 案例（RAG 入库）、`data/eval/eval_v1.json` 评测集
- [x] 接口文档：`docs/roadmind/API.md`、`docs/roadmind/CONTRACTS.md`
- [x] 部署：`docker-compose.yml` + `backend/Dockerfile` + `frontend/Dockerfile`
- [x] 测试：`cd backend && pytest`（16 项，覆盖主链路 / 鉴权 / WS / RAG 回归）
- [x] 演示说明：本 RUNBOOK
- [ ] 现场演示环境（P1 彩排时由 P2 起环境）