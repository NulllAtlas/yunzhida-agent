# SCENE-SCHEMA.md · scene.json 结构 v2（同步组员骨架 models.py）

> 版本：v2.0（2026-09-28，与 `backend/app/schemas/models.py` 对齐）
> 感知模块（M1）输出，供判定（M3）、应急（M4）、前端（M6）消费。

## scene.json 结构

```json
{
  "scene_id": "case_adf72a071510",
  "source": "text",
  "vehicles": [
    {
      "id": 1,
      "type": "car",
      "trajectory": [
        { "t": 0.0, "x": 0.5, "y": 0.7, "speed_kmh": 50.0 }
      ],
      "max_speed_kmh": 50.0
    }
  ],
  "events": [
    { "time": 12.0, "type": "rear_end", "participants": [1, 2], "keyframe": null }
  ],
  "road": "urban_intersection",
  "lane_markings": "dashed",
  "traffic_light": "unknown",
  "visibility": "day",
  "confidence": 0.6
}
```

## 字段说明

| 字段 | 说明 |
| --- | --- |
| `source` | 来源：`mock` / `video` / `text` |
| `vehicles[].type` | `car` / `truck` / `motorcycle` / `bicycle` / `pedestrian` |
| `vehicles[].trajectory` | 时间序列：时间 t(s)、归一化坐标 x/y(0-1)、速度 speed_kmh |
| `events[].type` | `collision` / `rear_end` / `vehicle_pedestrian` / `near_miss` / `signal_change` 等 |
| `events[].participants` | 参与对象的 id 列表 |
| `road` / `lane_markings` / `traffic_light` / `visibility` | 道路/信号/能见度场景要素 |
| `confidence` | 场景置信度 0-1，低则触发补录 |

## 降级规则

- `confidence` 过低或 `vehicles` 为空 → 前端转**文字补录**，以 `text_description` 重新触发判定。
- MVP 阶段所有 `source` 为 `text`（由 `services/perception.py` mock 生成）。
