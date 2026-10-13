# 云智达 · 交通事故辅助研判智能体

> **项目功能总说明（唯一权威版）** · 最后与代码核对：2026-10-14
>
> 这份文件回答三个问题：**现在能做什么、怎么跑起来、边界在哪**。
> 写的都是代码里真有的事；没实现或默认不生效的，一律在 §8 明说。
> 深度专题（接口契约、scene 结构、判责规则、运维）见 §10 文档索引。

---

## 1. 它解决什么

一起小事故之后，车主当场要知道"人要不要紧、该不该打 120/122、车停哪、三角牌摆多远"，
事后还要跟保险公司、交警说清"到底谁的责任"；交警端则要从头做一遍同样的判断。

云智达把这两件事自动化：**上传一段行车记录仪视频（或几张现场照片 + 几句话），
系统自动跑完"感知 → 取证 → 判责 → 处置"**，给车主一段能直接照做的处置建议，
给交警一份可导出的责任认定书草稿。

## 2. 两条主流程

**车主端（`:8000` 主界面的「📷 车主端」页签）**

上传视频 / 照片 / 纯文字 → 实时看到视频关键帧（标注了事故车辆识别框）→
得到事故类型、责任倾向、置信度、应急处置步骤 → 可继续追问，助手结合研判上下文回答
→ 需要时点 📞 进入实时语音对话，助手把结论念出来。

**监控端（同界面「🖥️ 监控端」页签）**

登录 → 案件列表 → 案件详情（依据 / 证据 / 理由分条）→ 推进状态、下发处理意见
→ 导出认定书草稿。与车主端通过 WebSocket 实时同步（车主能看到交警下发的消息，
交警能看到车主回执）。

**设备侧自动取证（B1）**：设备在事故发生时上报滚动录像 + 触发时刻，
后端按触发点回退 30 秒截出片段（只把含"事发前画面"的证据送进研判），
避免手动上传常常只剩事故后画面的问题。

## 3. 系统架构

### 3.1 智能体图（LangGraph，真并行）

```
perceive ──> retrieve ──> accident_gate ──┬──> judge   ──┐
                                          └──> respond ──┴──> aggregate
```

| 节点 | 干什么 | 关键实现 |
| --- | --- | --- |
| `perceive` | 视频/照片/文字 → `scene`（目标轨迹、碰撞事件、信号灯、路口要素） | `app/algo/video_tracker.py`（YOLOv8 track + 碰撞几何 + 信号灯 HSV 投票）、`app/services/scene_elements.py`（大模型看关键帧认路口要素，可选） |
| `retrieve` | 检索可引用的法条 / 案例 | `app/services/rag.py`（内置池 6 条；chromadb 可选，默认 keyword 检索） |
| `accident_gate` | **纯确定性**判断"这是不是真事故" | `app/algo/accident_gate.py`：最高目标速度 ≥10km/h **且** 最高碰撞置信度 ≥0.6，双门槛才通过 |
| `judge` | 责任研判 | `app/services/llm.py`：LLM 归类 + 责任比例 + 法条依据 + 理由分条；解析失败回退规则式判定 |
| `respond` | 当下应急处置 | 120/122、三角牌距离、撤离时机等模板 + LLM 润色 |
| `aggregate` | 汇总两条分支的结论并落库 | `app/graph/nodes/aggregate.py` |

`judge` 与 `respond` 并行、互不等待，但都消费 `accident_gate` 的**同一份结论** ——
不会出现"判责说非事故、应急却让你摆三角牌"的自相矛盾。

### 3.2 分层与技术栈

| 层 | 用了什么 |
| --- | --- |
| 感知 | `ultralytics` YOLOv8s（检测+追踪）、OpenCV（HSV 信号灯判色、抽帧、片段截取）、视觉大模型（路口要素，可选） |
| 编排 | `langgraph` 0.2 + `langchain-openai` 0.3 |
| 模型 | 移动云 MoMA 网关（OpenAI 兼容）：`deepseek-v4-flash` 判责/应急、`SenseVoice` 转写、视觉模型认路口要素；全程可 mock 跑通 |
| 服务 | `fastapi` 0.142 + uvicorn；SQLite 落库（案件、时间线、聊天记录） |
| 交互 | Gradio 6 工作台（`:8000/`，主界面）；Vue3（品牌首页 + 登录页）；WebSocket 双端推送 |
| 语音 | `SenseVoice`/`faster-whisper` 转写 + `edge-tts` 合成 + 浏览器本地语音兜底 |
| 部署 | `docker-compose.yml`（api + web 两个服务 + 数据卷）、`deploy/docs/RUNBOOK.md` |

## 4. 功能清单（当前代码里真有的）

| # | 功能 | 状态 | 说明 |
| --- | --- | --- | --- |
| 1 | 视频感知：检测 + 追踪 + 碰撞事件 | ✅ | YOLOv8 track；输出目标轨迹、速度、碰撞时刻双方识别框、标注关键帧 |
| 2 | 碰撞形态判定 | ✅ | 同向（追尾）/ 交叉 / 斜向 / 无法判定，由双方行进方向夹角算出 |
| 3 | 信号灯逐灯颜色 | ✅ | 裁剪灯框做 HSV 逐帧投票；多方向并存时汇总为 `mixed` |
| 4 | **大模型识别路口要素** | ⚠️ **默认不生效** | 认信号灯归属方向、人行横道、停止线、标志牌、路型、天气；见 §8.1 |
| 5 | 长视频智能分段 | ⚠️ | 超 300s 先用大模型找出关键片段再精算；依赖同一模型能看图 |
| 6 | 现场照片单帧检测 | ✅ | 作为补充证据进判定（不参与门控，静态画面没有运动学） |
| 7 | 文字描述要素抽取 | ✅ | 从车主补充文字里抽信号灯归属、标志牌、过错关键词；标成"用户陈述"进上下文 |
| 8 | 事故门控 | ✅ | 双门槛，纯代码判定，不交给 LLM 波动 |
| 9 | 责任研判 + 法条引用 | ✅ | 实际收敛为 **3 类**（追尾 / 普通碰撞 / 单方撞击公共设施），见 §8.2 |
| 10 | 应急处置步骤 | ✅ | 紧急度分级、报警电话、三角牌距离、撤离时机 |
| 11 | 知识检索（RAG） | ✅ | 内置 6 条（4 法条 + 2 案例），可换 chromadb |
| 12 | 车主端对话式研判 | ✅ | 传视频/照片/文字任意组合；可追问；回答结合研判上下文 |
| 13 | 监控端案件工作台 | ✅ | 登录、案件列表/详情、状态流转、下发意见、认定书草稿导出 |
| 14 | 双端实时推送 | ✅ | WebSocket 事件流，按 `owner_id` 过滤可见性 |
| 15 | 设备自动取证入口 | ✅ | 触发点回退 30s / 事后 5s 截片段，截取失败降级用原视频 |
| 16 | 实时语音对话（电话模式） | ✅ | WebSocket 全双工：转写 → LLM → 合成 → 播报；静音分句、打断、语气词 |
| 17 | 语音输入（按住说话） | ✅ | 单次录音 → 转写 → 填入输入框自动发送 |
| 18 | 语音播报开关 | ✅ | 🔊 一键开关；关掉即刻静音，含电话模式的语气词 |
| 19 | 通话分段字幕 | ✅ | 连续说话时每 2 秒把"正在说的话"上屏（停顿后仍一次发送完整消息） |
| 20 | 运行时切换大模型 | ✅ | 界面右上角模型管理，走 `/api/config/llm` |
| 21 | 评测集 | ✅ 数据 / ❌ 结果 | `data/eval/eval_v1.json` 有 10 个场景，仓库里**没有任何实测结果** |

## 5. 目录结构

```
yunzhida-agent/
├── backend/
│   ├── app/
│   │   ├── algo/            # 纯算法：视频追踪、碰撞几何、信号灯判色、门控、场景摘要
│   │   ├── api/routers/     # auth / cases / police / interact / progress / config / chat / tts / stt / voice_chat
│   │   ├── core/            # 配置、SQLite、日志、鉴权
│   │   ├── graph/           # LangGraph：state / builder / nodes(perceive,retrieve,gate,judge,respond,aggregate)
│   │   ├── schemas/         # Pydantic 模型（Scene / Judgment / EmergencyResponse …）
│   │   ├── services/        # 感知、LLM、RAG、STT、TTS、视频分段、路口要素识别
│   │   └── ui/gradio_ui.py  # 主界面（车主端对话 + 监控端工作台 + 通话视图）
│   ├── tests/               # 128 项 pytest
│   └── run_dev.bat          # 本地起后端
├── frontend/                # Vue3：品牌首页 + 登录页（+ 实时语音组件）
├── docs/                    # 本文件 + roadmind/ 专题文档
├── data/                    # 案例库（10 篇）、评测集（10 场景）
├── deploy/docs/RUNBOOK.md   # 运维手册
├── docker-compose.yml
└── .env.example             # 环境变量模板（真实 .env 绝不提交）
```

## 6. 快速开始

```bash
git clone https://github.com/NulllAtlas/yunzhida-agent.git
cd yunzhida-agent
cp .env.example .env        # 填入 MoMA 网关 Key（不填也能跑：默认 mock）
```

**本地开发**

```bash
# 后端 + 主界面（Gradio）→ http://localhost:8000
cd backend && ./run_dev.bat          # 等价于 uvicorn app.main:app --reload --port 8000

# 前端首页（可选）→ http://localhost:8080
cd frontend && npm install && npm run dev
```

**容器一键起**

```bash
docker compose up --build    # web:8080（Vue）/ api:8000（Gradio 主界面 + /docs API 文档）
```

**跑测试**

```bash
cd backend && pytest -q      # 128 项
```

> 默认 `USE_MOCK=true`，无凭据即可跑通全链路（返回标好的模拟结论）。
> 接真实模型请设 `USE_MOCK=false` 并填 `MOMA_API_KEY` / `MOMA_BASE_URL` / `MODEL_STRONG`。

## 7. 配置（`.env` 关键项）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `MOMA_BASE_URL` / `MOMA_API_KEY` | 空 | 移动云 MoMA 网关（OpenAI 兼容） |
| `USE_MOCK` | `True` | 真跑请设 `False` |
| `MODEL_STRONG` / `MODEL_FAST` | 空 | 判责与对话用的模型 ID（`MODEL_FAST` 目前无调用点） |
| `VIDEO_LLM_MODEL` | `Qwen2.5-VL-32B-Instruct` | 长视频分段 + 路口要素识别用的**视觉**模型，见 §8.1 |
| `VISION_SCENE_ENABLED` / `VISION_SCENE_FRAMES` | `True` / `4` | 路口要素识别开关与抽帧数 |
| `GATE_MIN_SPEED_KMH` / `GATE_MIN_EVENT_CONF` | `10` / `0.6` | 事故门控双门槛 |
| `ALGO_MODEL_NAME` / `ALGO_CONF` / `ALGO_VID_STRIDE` | `yolov8s.pt` / `0.3` / `2` | 检测模型与抽样步长 |
| `LONG_VIDEO_THRESHOLD` | `300` | 超过该秒数启用长视频分段 |
| `VOICE_CHAT_MODEL` / `VOICE_CHAT_TIMEOUT_S` | — | 电话模式用的模型与超时 |
| `STT_GATEWAY_MODEL` | `SenseVoice` | 网关转写模型；失败回退本地 faster-whisper |
| `TASK_TIMEOUT_S` / `MAX_CONCURRENCY` | `600` / `4` | 单任务超时与并发 |

## 8. 能力边界与演示禁区（重要）

> 这一节是为了**不把没做到的事说成做到了**。演示、答辩、材料都按这来。

### 8.1 大模型路口要素识别默认不生效

`app/services/scene_elements.py` 能让视觉模型认出**信号灯归属方向**（正对镜头那组灯是什么颜色）、
人行横道、停止线、标志牌、路型、天气 —— 这正是 YOLO+HSV 给不出的那层"灯管哪一方"的信息。

但它**依赖所配置的模型真的能看图**：仓库里 `.env` 把 `VIDEO_LLM_MODEL` 指向的模型实测
收图后返回空串（看不见图），代码按设计**静默退回原有模式**（YOLO+HSV），链路不受影响、
也不会有任何提示。要让这个功能生效，把 `VIDEO_LLM_MODEL` 换成实测可用的视觉模型
（`Qwen2.5-VL-32B-Instruct` / `Qwen2.5-VL-72B-Instruct`）并重启。

### 8.2 事故类型只有 3 类

LLM 判定与规则兜底实际都只覆盖 **追尾 / 普通碰撞 / 单方撞击公共设施**，
外加 `unknown` 与"非事故"。案例库虽有 10 类（含闯红灯、行人、逆行…），
但**判定能力不是 10 类**。

### 8.3 闯红灯要靠"归属"才判得出

检测侧只能给出"路口同时有红灯和绿灯"（多方向并存），据此**不能**认定某一方闯红灯。
可行路径只有两条：① 开 §8.1 的视觉识别，让模型指出"正对镜头那组是什么颜色"；
② 车主在文字里说清（"我直行是绿灯，对方闯红灯"）。否则一律输出 `unknown`。

### 8.4 其他已知局限

- **非机动车 / 行人**：YOLO 类别覆盖，但轨迹与碰撞判定明显弱于机动车。
- **2D 投影 ≠ 真实碰撞**：像素距离推距离，门控是启发式，不是物理测量。
- **RAG 规模**：内置池只有 6 条（4 法条 + 2 案例），不是"海量法条库"。
- **无任何准确率数字**：`data/eval/eval_v1.json` 有 10 个评测场景，但**从未跑出结果**，
  材料里不要引用命中率/准确率。
- **语音播报**：服务端 `edge-tts` 在当前网络下握手常态 403（换域名、换参数、最新版均无效），
  现在由**浏览器本地语音**兜底出声 —— 音色取决于浏览器里装了什么，别写成"云端合成晓晓音色"。
- **Vue 前端**：只有品牌首页与登录页，主界面是后端托管的 Gradio 工作台。
- **`MODEL_FAST`**：无任何调用点，是空字段，别写成"快慢模型两级路由"。

### 8.5 演示用什么素材

手上的样本里**多数是"标题卡片"（画面被大字覆盖）或与交通无关的画面**，模型会如实回答
"无法辨识"。演示请用真实行车记录仪素材（仓库样本中 `07cb5c79e332.mp4` 是真路面：十字路口 +
人行横道 + 停止线 + 白天）。

## 9. 测试与质量

- `backend/tests/` 共 **128 项 pytest**，覆盖门控、判责回退、链路回归、双端联动、
  语音诊断、路口要素识别（含"模型看不见图必须静默退回"等负例）。
- 跑法：`cd backend && pytest -q`。
- 约定：新增能力要带负例测试（异常/降级路径），不能只测顺利路径。

## 10. 文档索引

| 文档 | 覆盖 | 状态 |
| --- | --- | --- |
| **`docs/PROJECT.md`（本文件）** | 项目总说明：功能、架构、跑法、边界 | ✅ 与代码同步（2026-10-14） |
| `docs/roadmind/SCENE-SCHEMA.md` | `scene.json` 字段与降级规则 | ⚠️ 待补 `vision` 字段与 `events[].boxes` |
| `docs/roadmind/RULES.md` | 判责规则与实现状态 | ✅ |
| `docs/roadmind/RESPONSE-TEMPLATE.md` | 应急步骤模板 | ✅ |
| `docs/roadmind/CASES.md` | 案例库索引 | ✅ |
| `docs/roadmind/API.md` | 后端接口契约 | ⚠️ 缺语音/对话/配置等新接口，`GET /` 与超时默认值已过时 |
| `docs/VOICE_CHAT_GUIDE.md` | 实时语音对话协议与实现 | ✅ |
| `docs/VOICE_TROUBLESHOOTING.md` | 语音电话排障 | ✅ |
| `deploy/docs/RUNBOOK.md` | 部署、换模型、加规则、排障 | ⚠️ 测试数与接口清单待更新 |
| `backend/README.md` / `frontend/README.md` | 各端开发说明 | ⚠️ 目录与接口清单待更新 |

> **仓库只保留代码需要的文档。** 已删除的 12 份（赛前规划、分工排期、需求、可行性、
> 架构方案、PPT 大纲，以及描述已移除功能的说明），需要时可从 git 历史取回：
> `docs/README.md`、`ACCIDENT_VOICE_CHAT_CHECK.md`、`ORCA_TRANSCRIPT_FEATURE.md`、
> `NEW_FEATURES_PPT_OUTLINE.md`、`NEW_FEATURES_GUIDE.md`、
> `roadmind/CONTRACTS.md`、`roadmind/P1-TODO.md`、`roadmind/REQUIREMENTS.md`、
> `roadmind/FEASIBILITY.md`、`roadmind/TEAM-ROLES.md`、`roadmind/TEAM-WORKFLOW.md`、
> `roadmind/ARCHITECTURE.md`（架构内容见本文件 §3）。
