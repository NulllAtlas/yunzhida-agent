# CONTRACTS.md · judgment.json / response.json 数据契约 v2（同步组员骨架 models.py）

> 版本：v2.0（2026-09-28，与 `backend/app/schemas/models.py` 对齐）

## judgment.json（责任判定，M3 输出）

```json
{
  "scene_id": "case_adf72a071510",
  "responsibility": {
    "party_1": "primary",
    "party_2": "none",
    "split": "100/0"
  },
  "basis": ["《道交法》第43条 同车道行驶后车应与前车保持安全距离"],
  "reasoning": ["后车未与前车保持足以采取紧急制动措施的安全距离", "前车无过错"],
  "confidence": 0.8,
  "note": "本结果为智能辅助研判建议，非最终裁定，请以交管部门认定为准。"
}
```

- `responsibility.party_1/party_2`：`primary`（主责）/ `secondary`（次责）/ `equal`（同责）/ `none`（无责）/ `unknown`（待定）。
- `split`：责任占比，如 `70/30`、`100/0`。
- `basis`：法条依据（RAG 检索得到）。
- `reasoning`：判定理由分条（D7 结构化细化）。
- `confidence` + `note`：辅助建议定位与免责声明。

## response.json（应急方案，M4 输出）

```json
{
  "scene_id": "case_adf72a071510",
  "accident_type": "rear_end",
  "priority": 2,
  "steps": [
    { "order": 1, "action": "开启双闪，停车熄火", "urgent": true },
    { "order": 2, "action": "放置三角警示牌（来车方向 50 米）", "urgent": true },
    { "order": 3, "action": "人员撤至安全地带，勿留在车道", "urgent": true },
    { "order": 4, "action": "无伤亡可先拍照固定证据后撤离至安全处协商", "urgent": false }
  ],
  "insurance": "拨打保险报案，保留现场照片与行车记录仪。"
}
```

- `accident_type`：`vehicle_pedestrian` / `rear_end` / `general` 等。
- `priority`：紧急度分级（1 最高，如伤亡/起火；2 一般）。MVP 用规则基模板，迭代接 LLM 润色。
- `steps`：分步动作，`urgent` 标记"立即"项（前端红色高亮）。
- `insurance`：保险报案指引。

## retrieving.json（检索结果，M2 输出，供 M3/前端）

```json
{
  "id": "law-043",
  "title": "道交法 第43条",
  "content": "同车道行驶的机动车，后车应当与前车保持足以采取紧急制动措施的安全距离……",
  "source": "law",
  "score": 0.8
}
```

- `source`：`law`（法条）或 `case`（案例）。
- `content`：作为判定智能体的检索上下文。
