# P1 队长 · 每日工作清单（RoadMind）

> 本人 PM/产品 + 业务。更新于 2026-10-07。
> 对应 `TEAM-WORKFLOW.md` / `TEAM-ROLES.md` 中 P1 的任务，标注进度。
> ✅ = 已完成并推送 ｜ ⬜ = 未开始 ｜ ⏳ = 待联调（依赖 P2/P3/P4）

---

## 📋 P1 每日任务明细

| Day | 任务 | 交付物 | 状态 |
|-----|------|--------|------|
| D1 | 需求与主流程（车主/交警流程 + 3 用例） | `REQUIREMENTS.md` | ✅ |
| D2 | 规则清单 v1（8 类事故要件+责任倾向） | `RULES.md` | ✅ |
| D3 | 用例/案例种子（10 判例，≤200 字带标签） | `CASES.md` + `data/cases/*.md` | ✅ |
| D4 | 评测集 v1（10 场景+期望结论） | `data/eval/eval_v1.json` | ✅ |
| D5 | 应急合规核对 → 应急标准模板 | `RESPONSE-TEMPLATE.md` | ✅ |
| D6 | 端到端试跑，记录 UX/业务口径问题 | `E2E-TRIAL.md`（模板） | ⏳ 待联调 |
| D7 | 判定口径 + 2 个演示场景剧本 | `CALIBRATION-AND-DEMO.md` | ✅ |
| D8 | 评测回归（跑 eval_v1 核对误判） | `REGRESSION-REPORT.md`（4/10 初版） | ✅ (初版) |
| D9 | 演示脚本定稿（3 段台词） | `DEMO-SCRIPT.md` | ✅ |
| D10 | 全流程彩排（真实视频演示集） | 彩排记录 | ⏳ 待联调 |
| D11 | 答辩定稿 | `PRESENTATION.md` | ✅ (大纲) |

---

## ▶ 剩余/待联调项

- **D6 / D10**：端到端试跑与彩排，需 P2 把前端接入 `/api/cases` 真链路、P3 补全判定规则、P4 构建前端，方可真正执行。
- **D8**：判定模块完善后重跑 eval_v1（当前 mock 4/10，目标 ≥8/10 或 low 兜底）。
- **D11**：依据最终演示与数据定稿。

## ⚠️ 需要跨成员协调的阻塞

1. **前端主链路未接通**：Owner 走 `/api/upload`（硬编码），未调用 `/api/cases` 的 LangGraph 五节点 → 需 P2 协调。
2. **判定规则覆盖不足**：mock 仅 3 类，`REGRESSION-REPORT.md` 显示 4/10 → P3 补全。
3. **演示部署**：后端静态托管需 `frontend/dist`，需先 `npm run build`（P4）。
