# RoadMind · 代码骨架

多智能体交通事故辅助研判系统的基础代码（MVP 阶段可运行）。

## 目录结构
```
roadmind/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI 入口
│   │   ├── core/config.py          # 配置（use_mock 开关）
│   │   ├── schemas/models.py       # Pydantic 数据模型（scene/judgment/response）
│   │   ├── graph/
│   │   │   ├── state.py            # LangGraph 状态
│   │   │   ├── builder.py          # 构图：perceive→retrieve→judge→respond→aggregate
│   │   │   └── nodes/              # 各智能体节点
│   │   ├── services/               # M1感知 / M2 RAG / LLM 服务（mock）
│   │   └── api/                    # REST 路由 + 任务管理
│   └── requirements.txt
└── frontend/
    └── index.html                  # 双视角（车主/交警）页面
```

## 快速启动（MVP，默认 mock，无需任何凭据）

```bash
cd roadmind/backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

打开 http://localhost:8000 即可使用双视角界面。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/health` | 健康检查 |
| POST | `/api/cases` | 创建案件，启动多智能体分析（见下方输入方式） |
| GET  | `/api/tasks/{id}/status` | 查询任务状态与进度 |
| GET  | `/api/tasks/{id}/result` | 查询最终结果（scene/judgment/response） |

### `/api/cases` 三种输入方式（D6 闭环，至少提供一种）

```json
// 1) 直接喂入检测出的 scene（跳过感知，推荐演示用）
{ "scene": { "$schema": "scene.v1.json", "vehicles": [] } }

// 2) 真实视频检测（迭代阶段，需配置 YOLO 路径）
{ "media_path": "D:/video/test2.mp4" }

// 3) 文字描述兜底（mock 模式无需任何凭借即可跑通）
{ "text_description": "路口我车直行，对方左转弯未让行发生碰撞" }
```

## 验证闭环（mock，无需真实模型）

```bash
cd roadmind/backend
python scripts/verify_chain_mock.py
```
输出：RAG 检索条数、责任判定（依据/理由/置信度）、应急步骤 —— 即 D6 闭环核心。
真实 LLM/视频感知接入见 `.env.example` 与 `app/services/`。

## 检测脚本（算法侧，需 ultralytics 环境）

| 脚本 | 作用 |
|------|------|
| `scripts/convert_to_scene.py` | 视频 → scene.json（去重 + 轨迹 + 关键帧） |
| `scripts/detect_count.py` | 快捷去重计数调试 |
| `scripts/byte_track_demo.py` | YOLO + ByteTrack 追踪 demo |

## 设计说明

- **功能不砍，精度递进**：MVP 阶段默认 mock（`use_mock=True`），全链路可跑、可演示；
  真实视频感知（YOLO）、LLM（MoMA 网关）、向量检索（chromadb）按 `.env` 配置接入。
- **多智能体交互**：LangGraph 状态图编排感知 → 检索 → 判定 → 应急 → 汇聚。
- **判定定位为辅助建议**：`judgment.note` 明确"非最终裁定"。
