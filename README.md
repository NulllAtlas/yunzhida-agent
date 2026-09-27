# RoadMind · 交通事故辅助研判智能体

> 面向"移动云杯"大赛的多智能体交通事故辅助研判系统。
> 队长(P1) 牵头 · 4 人团队 · 11 天迭代。

## 项目简介

RoadMind 是一个基于**视频感知 + 多智能体研判**的交通事故辅助系统，服务两类用户：

- **车主**：上传行车记录仪视频 → 即时获得"是否拨打 120/122"级联提示、应急处置步骤、责任预判概览。
- **交警**：上传/选择案件 → 查看责任认定详情（依据 + 证据 + 理由分条）→ 导出认定书草稿。

## 仓库结构

```
.
├── docs/roadmind/          # 文档：需求 / 规则 / 契约 / 应急模板 / 演示脚本
├── data/                   # 案例库 / 评测集
│   ├── cases/
│   └── eval/
├── backend/                # FastAPI + LangGraph 后端
│   ├── app/                # 应用入口 / 路由 / 模型 / 数据契约
│   ├── graph/              # 多智能体图：perceive → judge → respond → aggregate
│   ├── services/           # rag / llm / judge / respond
│   ├── Dockerfile
│   └── docker-compose.yml
└── frontend/               # Vue3 + Vite 前端（车主端 / 交警端）
```

## 快速开始

见 `backend/README.md` 与 `frontend/README.md`。整体启动方式见 `docs/roadmind/DEPLOY.md`（D9 产出）。

## 团队排期

- 每日任务：`docs/roadmind/` 下按 D1–D11 产出。
- 排期总表：见分工文档 `TEAM-WORKFLOW`（P1 队长维护）。

## 文档索引

| 文档 | 内容 | 产出自 |
| --- | --- | --- |
| `docs/roadmind/REQUIREMENTS.md` | 需求与主流程（Day1） | P1 |
| `docs/roadmind/RULES.md` | 8 类事故规则清单（Day2） | P1 |
| `docs/roadmind/API.md` | 后端接口契约（Day1） | P2 |
| `docs/roadmind/SCENE-SCHEMA.md` | scene.json 结构（Day1） | P3 |
| `docs/roadmind/RESPONSE-TEMPLATE.md` | 应急步骤模板（Day5） | P1 |
| `docs/roadmind/DEMO-SCRIPT.md` | 演示脚本（Day9） | P1 |
