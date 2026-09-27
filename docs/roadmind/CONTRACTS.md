# CONTRACTS.md · judgment.json / response.json 数据契约 v1（Day1）

> 版本：v0.1（2026-09-27）· P2(+P3) 定义，P4 消费。

## judgment.json（责任判定）

```json
{
  "case_type": "rear_end",
  "verdict": {
    "parties": [
      { "object_id": "obj_1", "role": "A", "liability_pct": 70, "main_reason": "未保持安全距离" },
      { "object_id": "obj_2", "role": "B", "liability_pct": 30, "main_reason": "突然变道" }
    ]
  },
  "reasoning": ["A 车未保持安全距离", "B 车突然变道"],
  "laws": [
    { "article": "《道路交通安全法》第 43 条", "summary": "同车道追尾事故责任" }
  ],
  "confidence": 0.78,
  "low_confidence": false,
  "needs_human_review": false,
  "summary_text": "依据现场视频，A 车追尾 B 车，A 车负主要责任（70%）。"
}
```

- `case_type`：`rear_end | lane_change | no_priority | red_light | turning_no_yield | reverse | wrong_way | car_pedestrian` 之一。
- `verdict.parties`：按对象给责任占比，合计 100。
- `reasoning`：理由分条（判定结构化，D7 细化）。
- `laws`：法条引用（RAG 检索得到）。
- `confidence` + `low_confidence` + `needs_human_review`：辅助建议的置信表达。

## response.json（应急方案）

```json
{
  "emergency_level": "high",
  "urgent_actions": [
    { "order": 1, "action": "立即拨打 120", "urgent": true, "checked": false }
  ],
  "steps": [
    { "order": 1, "action": "开启双闪，熄火", "urgent": false, "checked": false },
    { "order": 2, "action": "距车后方 50 米放置三角警示牌", "urgent": true, "checked": false },
    { "order": 3, "action": "人员撤离至安全区域", "urgent": true, "checked": false },
    { "order": 4, "action": "拨打 122 报警并留存证据", "urgent": false, "checked": false }
  ],
  "insurance_note": "48 小时内报保险，保存现场照片与记录仪视频",
  "level_label": "需要立即报警/呼叫救护",
  "confidence": 0.8
}
```

- `emergency_level`：`high`（伤亡/起火/翻车）| `medium` | `low`。
- `urgent_actions`：强提示动作（红色弹层展示）。
- `steps`：分步动作，前端可勾选完成。
- `insurance_note`：保险报案指引。
