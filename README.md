# 云智达小队 · 2026移动云杯模型应用赛

2026年"移动云杯"智算应用创新大赛 — 模型应用赛参赛项目仓库。
基于移动云 MoMA 平台构建智能体（Agent）应用。

本次参赛作品 **云智达 · 交通事故辅助研判智能体**：基于**视频感知 + 多智能体研判**的事故辅助系统，服务两类用户：

- **车主**：上传行车记录仪视频 → 即时获得"是否拨打 120/122"级联提示、应急处置步骤、责任预判概览。
- **交警**：上传/选择案件 → 查看责任认定详情（依据 + 证据 + 理由分条）→ 导出认定书草稿。

> 仓库结构说明：原 `agent/` 归档子目录的内容已提升至仓库根目录，仓库当前以单一项目根目录组织，`backend/`、`frontend/`、`docs/`、`data/`、`deploy/` 直接位于根下。

## 仓库结构

```
yunzhida-agent/
├── docs/        # 项目总说明 + 专题文档 + 过程归档
│   ├── PROJECT.md                     # ★ 项目功能总说明（先看这份）
│   └── roadmind/                      # 架构 / 判责规则 / scene 结构 / 接口契约
├── data/        # 案例库 / 评测集
│   ├── cases/
│   └── eval/
├── backend/     # FastAPI + LangGraph 后端，并托管主界面
│   └── app/ui/gradio_ui.py            # ★ 真正的双端界面（车主端对话 + 监控端工作台）
├── frontend/    # Vue3：品牌首页 + 登录页
├── deploy/docs/ # 部署与运维文档（RUNBOOK）
├── docker-compose.yml # 一键容器化部署（api + 前端静态）
└── .env.example # 环境变量模板（真实.env绝不提交）
```

> 注意：**主界面不在 Vue 里**。`:8000/` 由后端 Gradio 工作台托管（车主端 + 监控端都在这一页），
> Vue 前端只保留品牌首页与登录页。

演示视频、大文件走群文件/网盘，**不要提交到本仓库**。

## 快速开始

```bash
git clone https://github.com/NulllAtlas/yunzhida-agent.git
cd yunzhida-agent
cp .env.example .env   # 然后把群里发的真实 Key 填进 .env
```

后端启动见 `backend/README.md`。MVP 默认 mock，无需凭据即可跑通。

**主界面在 `http://localhost:8000`**（后端托管的 Gradio 工作台：车主端对话 + 监控端，
视频/照片/文字上传与研判、语音对话都在这里）；Vue 前端（`:8080`）只有首页与登录页。

容器化一键启动（需 Docker）：

```bash
docker compose up --build   # 前端 http://localhost:8080 ，后端 http://localhost:8000/docs
```

## 文档索引（云智达）

**先看** [`docs/PROJECT.md`](docs/PROJECT.md) —— 项目功能总说明：能做什么、怎么跑、
能力边界与演示禁区（含"哪些功能默认不生效"，写材料前务必对照）。

专题文档：

| 文档 | 内容 |
| --- | --- |
| `docs/roadmind/ARCHITECTURE.md` | 多智能体架构设计与感知能力缺口 |
| `docs/roadmind/SCENE-SCHEMA.md` | `scene.json` 结构与降级规则 |
| `docs/roadmind/RULES.md` | 事故判责规则清单与实现状态 |
| `docs/roadmind/RESPONSE-TEMPLATE.md` | 应急步骤标准模板 |
| `docs/roadmind/CASES.md` | 案例库索引 |
| `docs/roadmind/API.md` | 后端接口契约 |
| `docs/VOICE_CHAT_GUIDE.md` | 实时语音对话（电话模式）实现与协议 |
| `docs/VOICE_TROUBLESHOOTING.md` | 语音电话排障 |
| `docs/NEW_FEATURES_GUIDE.md` | 语音 / 长视频分段功能的配置与用法 |
| `deploy/docs/RUNBOOK.md` | 部署 / 换模型 / 加规则 / 排障 |

过程归档（赛前规划，其中排期已作废）：`docs/roadmind/` 下 `REQUIREMENTS.md`、
`FEASIBILITY.md`、`TEAM-ROLES.md`、`TEAM-WORKFLOW.md`。

## 协作约定

1. **分支**：`main` 只放能跑的版本；开发在自己的 `feat-名字-功能` 分支（如 `feat-lyaoyu-login`），完成后发起 Pull Request，找一个人看一眼再合并。
2. **提交信息**：一句话说清楚做了什么，如 `完成意图识别模块初版`。
3. **密钥安全**：`.env` 已在 `.gitignore` 中，任何情况下不要把 API Key 写进代码或提交到仓库。
4. **冲突预防**：改别人负责的目录前先在群里说一声。

## 评分维度 → 分工对照（每人盯一块）

| 评审维度（25分） | 负责人 | 对应材料 |
|---|---|---|
| Agent设计合理性 | 【待定】 | 问题定义、目标用户、能力设计 |
| 技术实现能力 | 【待定】 | 架构、Prompt工程、MoMA模型清单与选型理由 |
| 应用价值与商业前景 | 【待定】 | 场景价值、商业模式 |
| 展示与文档 | 【待定】 | PPT、演示视频、答辩 |
