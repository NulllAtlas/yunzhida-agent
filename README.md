# 云智达小队 · 2026移动云杯模型应用赛

2026年"移动云杯"智算应用创新大赛 — 模型应用赛参赛项目仓库。
基于移动云 MoMA 平台构建智能体（Agent）应用。

本次参赛作品 **RoadMind · 交通事故辅助研判智能体**：基于**视频感知 + 多智能体研判**的事故辅助系统，服务两类用户：

- **车主**：上传行车记录仪视频 → 即时获得"是否拨打 120/122"级联提示、应急处置步骤、责任预判概览。
- **交警**：上传/选择案件 → 查看责任认定详情（依据 + 证据 + 理由分条）→ 导出认定书草稿。

## 仓库结构

```
yunzhida-agent/
├── docs/        # 作品说明书、PPT定稿、评审材料归档
│   └── roadmind/                      # RoadMind 方案/架构/分工/契约/脚本
├── data/        # 案例库 / 评测集
│   ├── cases/
│   └── eval/
├── agent/       # MoMA平台侧资产：Prompt设计、工作流编排、配置导出
├── backend/     # FastAPI + LangGraph 后端（perceive→retrieve→judge→respond→aggregate）
├── frontend/    # Vue3 双端前端（车主端 / 交警端）
├── deploy/docs/ # 部署与运维文档（RUNBOOK）
├── docker-compose.yml # 一键容器化部署（api + 前端静态）
└── .env.example # 环境变量模板（真实.env绝不提交）
```

演示视频、大文件走群文件/网盘，**不要提交到本仓库**。

## 快速开始

```bash
git clone <仓库地址>
cd yunzhida-agent
cp .env.example .env   # 然后把群里发的真实 Key 填进 .env
```

后端启动见 `backend/README.md`。MVP 默认 mock，无需凭据即可跑通。

容器化一键启动（需 Docker）：

```bash
docker compose up --build   # 前端 http://localhost:8080 ，后端 http://localhost:8000/docs
```

## 文档索引（RoadMind）

| 文档 | 内容 | 产出自 |
| --- | --- | --- |
| `docs/roadmind/REQUIREMENTS.md` | 需求与主流程（Day1） | P1 |
| `docs/roadmind/ARCHITECTURE.md` | 多智能体架构设计 | P1/P2 |
| `docs/roadmind/TEAM-ROLES.md` | 分工与 11 天排期 | P1 |
| `docs/roadmind/TEAM-WORKFLOW.md` | 个人任务流程 | P1 |
| `docs/roadmind/FEASIBILITY.md` | 可行性评估 | P1 |
| `docs/roadmind/RULES.md` | 8 类事故规则清单（Day2） | P1 |
| `docs/roadmind/CASES.md` | 典型案例判例库索引（Day3） | P1 |
| `docs/roadmind/RESPONSE-TEMPLATE.md` | 应急步骤标准模板（Day5） | P1 |
| `docs/roadmind/API.md` | 后端接口契约 | P2 |
| `docs/roadmind/SCENE-SCHEMA.md` | scene.json 结构 | P3 |
| `docs/roadmind/CONTRACTS.md` | judgment/response 契约 | P2+P3 |
| `docs/roadmind/DEMO-SCRIPT.md` | 演示脚本（Day9） | P1 |
| `deploy/docs/RUNBOOK.md` | 后端部署 / 换模型 / 加规则 / 排障 | P2 |

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
