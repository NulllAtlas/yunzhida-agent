# 判定回归报告 v0.1（Day8 · P1 队长）

> 版本：v0.1（2026-10-07，Day8 初版）
> 方法：用现有判定模块（`backend/app/services/llm.py` 的 mock 规则）对 `data/eval/eval_v1.json` 全量 10 场景回归。
> 结论初版：**4/10 命中**。原因清晰，供 P3 调判定逻辑用。

---

## 1. 回归结果表

| id | 场景 | 判定结果 | 置信 | 低置信 | 期望 | 结论 |
|----|------|---------|------|--------|------|------|
| e01 | 高速追尾 | primary/none | 0.8 | 否 | primary/none | ✅ |
| e02 | 变道刮蹭 | primary/none | 0.8 | 否 | primary/none | ✅ |
| e03 | 无信号灯路口未让右 | primary/secondary | 0.8 | 否 | primary/secondary | ✅ |
| e04 | 转弯未让直行 | primary/secondary | 0.8 | 否 | primary/none | ❌ |
| e05 | 闯红灯 | primary/secondary | 0.8 | 否 | primary/none | ❌ |
| e06 | 倒车碰撞 | unknown | 0.3 | 是 | primary/none | ❌ |
| e07 | 逆行迎面相撞 | unknown | 0.3 | 是 | primary/none | ❌ |
| e08 | 斑马线未让行撞行人 | primary/secondary | 0.8 | 否 | primary/none | ❌ |
| e09 | 行人闯红灯（减责） | primary/secondary | 0.8 | 否 | secondary/primary | ❌ |
| e10 | 要素不足（夜间） | unknown | 0.3 | 是 | unknown（兜底） | ✅ |

**命中率：4/10。**

---

## 2. 误判原因分析（反馈 P3）

### 2.1 规则覆盖不足（e06、e07）
- 现有 mock 仅有 3 类规则（追尾/变道/路口）。
- **缺**：倒车、逆行、闯红灯、转弯未让行、车-行人。这些场景落入 default → `unknown` + 低置信。
- **修复方向**：在 `_RULE_JUDGMENTS` 中补齐全 8 类规则（对应 `RULES.md`），或接入真实 LLM。

### 2.2 "路口"规则过度匹配（e04、e05、e08、e09）
- "路口/未让行"关键词命中过宽，导致**转弯、闯红灯、撞行人**全部误判为 70/30。
- 根因：单一关键词匹配，无法区分具体过错类型。
- **修复方向**：引入**要件级判定**——结合 `scene.events.type`（rear_end/lane_change/collision 等）与更多关键词组合，而不是仅看"未让行"。

### 2.3 置信度取值粗糙
- 所有命中规则固定 0.8，未随场景完整度/夜间/遮挡调整。
- **修复方向**：按 `perception.confidence` 与场景因素缩放置信度；要素不足时强制 low。

---

## 3. 对 P3 的行动项

1. **补全规则**：mock 阶段至少覆盖 8 类事故（可先基于 `RULES.md` 扩展 `_RULE_JUDGMENTS`）。
2. **细化过错识别**：用于判定的关键词/特征要能区分具体事故类型，避免"路口"一刀切。
3. **置信度校准**：动态置信 + 低置信兜底（对齐 `CALIBRATION-AND-DEMO.md` 分级口径）。
4. **接真实 LLM 后**：本报告作为基准，重跑 eval_v1 对比（目标 ≥8/10 或 low 兜底达标）。

---

## 4. 说明

- 本初版基于 mock 判定逻辑真实运行得出；待 P3 判定模块完善后重跑。
- 期望口径见 `CALIBRATION-AND-DEMO.md`（A/B/C 三级）与 `eval_v1.json` 断言。
