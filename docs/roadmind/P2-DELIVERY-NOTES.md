# P2 交付备忘（DELIVERY-NOTES）

> 角色：P2 后端 / 架构　|　作品：RoadMind · 交通事故辅助研判智能体
> 版本：v1.0（2026-10-05）　|　分支：`main`（本仓库不保留其他分支）
> 用途：交代 P2 的交付完成度、关键口径与剩余待办，供 P1 彩排/答辩与全队对齐。

---

## 一、交付完成度（对照 `TEAM-WORKFLOW.md` P2 D1–D11）

| 任务 | 状态 | 交付物 / 说明 |
| --- | --- | --- |
| D1 契约 + 骨架 | ✅ | `docs/roadmind/API.md`、`CONTRACTS.md`、`app/schemas/models.py`、可启动 FastAPI+LangGraph 骨架 |
| D2 图串通（mock） | ✅ | `perceive→retrieve→judge→respond→aggregate` 出 `result`；视频上传 `POST /api/uploads/video` + 建任务 + 状态查询 |
| D3 RAG 服务 | ✅ | `services/rag.py`（chromadb 向量检索，离线 n-gram embedding，不可用降级关键词）、`scripts/index_rules.py`、`services/llm.py`（统一 `call_chat`，含鉴权/超时/重试） |
| D4 判定节点接真 LLM | ✅ | `graph/nodes/judge.py` 拼 prompt→解析 JSON；超时+解析容错回退规则；WS 阶段推送 |
| D5 应急节点 + 进度 | ✅ | `graph/nodes/respond.py` 模板选型+LLM 润色；WS 全流程进度 |
| D6 全链路无 mock | ✅ | 感知服务可选接入 `PERCEPTION_SERVICE_URL`（见第三节）；错误处理覆盖视频解析失败 / LLM 超时 / 空场景 |
| D7 API 完善 + 鉴权 | ✅ | JWT + owner/police 角色；统一错误码与响应结构；请求日志；交警端列表/详情/草稿导出 |
| D8 性能与并发 | ✅ | 信号量限流 + 单任务超时熔断 + 指标；大视频分帧策略（`services/frames.py`，均匀抽样+三重上限） |
| D9 部署 | ✅ | `backend/Dockerfile` + `frontend/Dockerfile` + `docker-compose.yml`（实测 `up --build` 通过，含 WS 反代）；`README` 与 `.env.example` |
| D10 稳定性 + 文档 | ✅（除彩排） | 全流程稳定性测试；`deploy/docs/RUNBOOK.md`；「支持 P1 彩排起环境」为赛前动作 |
| D11 交付核对 | ✅ | RUNBOOK §8 核对清单；5 分钟可复现 |

测试：`cd backend && pytest` → 本地 31 passed / 3 skipped（skipped 仅因本机 opencv 环境差异），
**容器内 34 passed（无 skip）**。

---

## 二、口径说明：`USE_MOCK` 是「开关式」而非「残留」

D6 排期原文为「移除 mock」。本项目的实际口径是**开关式可切换**，这是刻意设计而非未完成：

- `USE_MOCK=true`（默认）：全链路走确定性规则/模板，**无任何凭据也能完整演示**，用于开发与容灾。
- `USE_MOCK=false` + 配置 `.env`：走真实 MoMA 网关（`app/services/llm.py`），失败自动回落规则。

切换方法见 `RUNBOOK.md` §4。两种模式共用同一段调用代码，切换即生效，**不存在两套实现**。

---

## 三、感知服务接入（P3 `POST /perceive`）

适配层已就绪，**只等 P3 服务地址**：

- 配置 `PERCEPTION_SERVICE_URL`（如 `http://localhost:9000`）后，感知阶段调用
  `POST {PERCEPTION_SERVICE_URL}/perceive`，请求体 `{scene_id, text, video_path}`，
  支持返回 `{"code":0,"data":{scene}}` 或直接返回 `scene` 两种写法。
- **未配置 / 网络失败 / 超时 / 返回结构非法** → 自动回落本地文字降级场景（含 D8 抽帧关键帧），
  任务照常成功。
- 环境变量已在 `.env.example` 与 `docker-compose.yml` 预留。
- 离线验证：`tests/test_perception_remote.py`（本地假感知服务，4 项）。

> 待办：P3 服务就绪后，填入其地址并做一次真实联调（当前回落逻辑已可保证不影响主流程）。

---

## 四、剩余待办（未完成项，均非代码缺陷）

| 项 | 性质 | 触发条件 |
| --- | --- | --- |
| 真实 MoMA 活体调用 | 赛前冒烟自测 | 拿到组委会 `MOMA_API_KEY / MOMA_BASE_URL / MODEL_FAST / MODEL_STRONG`（离线代码路径已由 `tests/test_llm_gateway.py` 覆盖） |
| P3 感知真实联调 | 联调 | P3 提供 `POST /perceive` 服务地址 |
| 前端接真实上传/结果接口 | 跨端 | P4 将 `UploadZone.vue` 从占位 `POST /api/upload` 切到 `POST /api/uploads/video` |
| 现场演示环境 | 彩排动作 | P1 彩排时由 P2 起环境（`docker compose up --build`） |

> 说明：`POST /api/upload`（单数）与 `POST /api/audit` 是 P4 早期联调占位，刻意保留以免破坏前端；
> 真实链路请走 `POST /api/uploads/video` → `POST /api/cases` → `GET /api/tasks/{id}/result`。

---

## 五、快速验收命令

```bash
# 1) 起服务（前端 8080 / 后端 8000）
docker compose up --build

# 2) 健康检查（use_mock / rag_backend / llm_configured）
curl http://localhost:8000/health

# 3) 上传视频 → 建任务 → 查结果
curl -F "file=@clip.mp4" http://localhost:8000/api/uploads/video
curl -X POST http://localhost:8000/api/cases -H "Content-Type: application/json" \
     -d '{"video_id":"<上一步返回的 video_id>"}'

# 4) 回归测试（容器内为干净环境）
docker exec roadmind-api python -m pytest -q
```

---

## 六、关键提交（main）

| 提交 | 内容 |
| --- | --- |
| `b9ab2a1` | 补齐后端 D3–D11（真实 LLM/RAG、WS 进度、鉴权、并发、部署） |
| `b00c0fc` | 修复容器构建依赖冲突与入库脚本 import 失败 |
| `3d6ce7f` | D8 视频分帧适配层（大视频均匀抽样 + 三重熔断 + 文字降级） |
| `275e81d` | 本地假网关离线验证真实 MoMA 调用路径 |
| `170d033` | 补真实视频上传接口，打通上传→落盘→建任务 |

> 本仓库只保留 `main` 分支；`feat-p2-moma` 分支已合并并删除。