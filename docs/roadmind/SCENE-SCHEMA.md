# SCENE-SCHEMA.md · scene.json 结构 v1（Day1 · P3 主导）

> 版本：v0.1（2026-09-27）。感知模块输出，供 judge、前端消费。

## scene.json 结构

```json
{
  "scene_id": "s_9f3c2",
  "source": {
    "video_id": "v_xxx",
    "fps": 30,
    "duration_s": 12.5,
    "resolution": { "width": 1920, "height": 1080 }
  },
  "objects": [
    {
      "id": "obj_1",
      "kind": "vehicle",
      "category": "car",
      "trajectory": [
        { "t": 0.0, "x": 40, "y": 60, "w": 8, "h": 12, "speed": 6.5, "heading": 0 }
      ],
      "keyframes": [2.0, 2.4, 3.0],
      "confidence": 0.91
    }
  ],
  "events": [
    {
      "type": "collision",
      "t": 2.3,
      "objects": ["obj_1", "obj_2"],
      "impact_speed": 12.0,
      "confidence": 0.82
    }
  ],
  "scene_factors": {
    "lighting": "day",
    "weather": "clear",
    "road_type": "intersection",
    "traffic_light": { "present": false, "state": null },
    "lanes_detected": false,
    "night": false,
    "occlusion": false
  },
  "confidence": 0.74,
  "low_confidence": false,
  "notes": ["可忽略的检测噪声"],
  "schema_version": "1.0"
}
```

## 字段说明

| 字段 | 说明 |
| --- | --- |
| `objects[].kind` | `vehicle` / `pedestrian` / `non_motor` / `other` |
| `objects[].trajectory` | 时间序列：位置(x,y,w,h)、速度(speed, m/s)、朝向(heading°) |
| `events[].type` | `collision` / `rapid_brake` / `lane_change` / `red_light` 等 |
| `scene_factors` | 场景因素，影响判定与置信度 |
| `confidence` | 场景置信度 0-1，低则触发补录 |
| `low_confidence` | `true` 时前端转文字/照片补录 |

## 降级规则

- `confidence < 0.5` 或 `objects` 为空 → `low_confidence = true` → 前端转补录表单。
- 夜间/遮挡（`night || occlusion`）→ 自动下调 confidence。
