# RoadMind · 场景 JSON Schema v1（SCENE-SCHEMA）

> 版本：v1.0（2026-09-26 · D1 冻结）
> 作者：P3（算法）
> 用途：M1 视频感知的输出契约，供 M3 判定 / M4 应急 / M5 编排 / M6 前端消费。
> 对应代码：`app/schemas/models.py`（`Scene` 类）
> 原则：**功能不砍、精度递进** —— 字段齐全保证功能完整；精度不足的字段允许为空/低置信，由前端或后续迭代补齐。

---

## 1. 顶层结构

```json
{
  "$schema": "scene.v1.json",
  "scene_id": "字符串，唯一",
  "source": "mock | video | photo | text",
  "vehicles": [ { 车辆/目标 } ],
  "events":    [ { 事件 } ],
  "road": "道路类型",
  "lane_markings": "车道线",
  "traffic_light": "信号灯",
  "visibility": "可见度",
  "confidence": 0.0
}
```

## 2. 字段明细

### 2.1 顶层

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `$schema` | string | 是 | 版本标识 `scene.v1.json` |
| `scene_id` | string | 是 | 唯一标识（一般 = 视频/案件 id） |
| `source` | enum | 是 | 数据来源：`mock`/`video`/`photo`/`text` |
| `vehicles` | array | 是 | 识别到的移动目标（车/人/非机动车），见 §3 |
| `events` | array | 是 | 关键事件/事故瞬间，见 §4 |
| `road` | string | 否 | 道路类型（`urban_intersection`/`highway`/`rural`/`unknown`） |
| `lane_markings` | string | 否 | 车道线：`dashed`/`solid`/`solid_yellow`/`none`/`unknown` |
| `traffic_light` | string | 否 | `red`/`green`/`yellow`/`no_signal`/`unknown` |
| `visibility` | string | 否 | `day`/`night`/`dusk`/`rain`/`fog`/`unknown` |
| `confidence` | float | 是 | 整体感知置信度 0–1（低精度阶段可低，驱动前端/降级提示） |

### 2.2 目标对象（vehicles[ ]）——也容纳"人物"

> 你的 YOLOv8 检测目标是**人物**，因此 `type` 必须支持人/非机动车。命名用 `vehicles` 仅为兼容既有代码，字段 `type` 决定实际类别。

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `id` | int | 是 | 目标唯一编号（追踪分配的 track id） |
| `type` | enum | 是 | `car` / `truck` / `bus` / `motorcycle` / `bicycle` / `pedestrian` / `other` |
| `class_conf` | float | 否 | YOLO 检测置信度 0–1 |
| `trajectory` | array | 否 | 轨迹点数组，见 §2.3 |
| `max_speed_kmh` | float | 否 | 该目标最大速度估算 |
| `bbox_at_collision` | object | 否 | 碰撞时刻的归一化框 `{x,y,w,h}`（便于前端标框展示） |

### 2.3 轨迹点（trajectory[ ]）

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `t` | float | 是 | 时间（秒，视频内） |
| `x` | float | 是 | 归一化横坐标 0–1（画面比例） |
| `y` | float | 是 | 归一化纵坐标 0–1 |
| `w` | float | 否 | 归一化宽 |
| `h` | float | 否 | 归一化高 |
| `speed_kmh` | float | 否 | 速度估算 |

### 2.4 事件（events[ ]）

| 字段 | 类型 | 必填 | 说明 |
|------|------|:---:|------|
| `time` | float | 是 | 事件时间（秒） |
| `type` | enum | 是 | `collision`(碰撞) / `near_miss`(险情) / `signal_change`(变灯) / `lane_change`(变道) / `other` |
| `participants` | array | 否 | 参与目标 id 列表 |
| `keyframe` | string | 否 | 关键帧图片相对/绝对路径 |
| `confidence` | float | 否 | 该事件检测置信度 |

---

## 3. 完整示例（追尾场景）

```json
{
  "$schema": "scene.v1.json",
  "scene_id": "case_001",
  "source": "video",
  "vehicles": [
    {
      "id": 1,
      "type": "car",
      "class_conf": 0.91,
      "trajectory": [
        {"t": 0.0,  "x": 0.50, "y": 0.70, "w": 0.08, "h": 0.10, "speed_kmh": 48.0},
        {"t": 12.3, "x": 0.60, "y": 0.68, "w": 0.09, "h": 0.11, "speed_kmh": 41.0}
      ],
      "max_speed_kmh": 50.0,
      "bbox_at_collision": {"x": 0.60, "y": 0.68, "w": 0.09, "h": 0.11}
    },
    {
      "id": 2,
      "type": "car",
      "class_conf": 0.88,
      "trajectory": [
        {"t": 0.0,  "x": 0.55, "y": 0.60, "speed_kmh": 10.0},
        {"t": 12.3, "x": 0.60, "y": 0.60, "speed_kmh": 5.0}
      ],
      "max_speed_kmh": 12.0,
      "bbox_at_collision": {"x": 0.60, "y": 0.60, "w": 0.09, "h": 0.11}
    }
  ],
  "events": [
    {"time": 12.3, "type": "collision", "participants": [1, 2], "keyframe": "keyframes/case_001_t12.3.jpg", "confidence": 0.85}
  ],
  "road": "urban_intersection",
  "lane_markings": "dashed",
  "traffic_light": "green",
  "visibility": "day",
  "confidence": 0.82
}
```

### 3.1 纯人物检测示例（你当前的 YOLO 输出 → 场景）

> 若只检测到人物（如事故现场的行人/司机），结构不变，`type=pedestrian`，便于后续判定"车撞行人"类责任。

```json
{
  "$schema": "scene.v1.json",
  "scene_id": "case_003",
  "source": "video",
  "vehicles": [
    {"id": 1, "type": "pedestrian", "class_conf": 0.93,
     "trajectory": [{"t": 0.0, "x": 0.4, "y": 0.5, "speed_kmh": 6.0}, {"t": 5.0, "x": 0.5, "y": 0.5, "speed_kmh": 8.0}],
     "bbox_at_collision": {"x": 0.5, "y": 0.5, "w": 0.05, "h": 0.15}}
  ],
  "events": [{"time": 5.0, "type": "collision", "participants": [1], "keyframe": "kf.jpg", "confidence": 0.7}],
  "road": "urban_intersection",
  "confidence": 0.6
}
```

---

## 4. 与代码的对应关系

`app/schemas/models.py` 中的 `Scene` / `Vehicle` / `SceneEvent` / `TrajectoryPoint` 与本 Schema 字段一一对应（`$schema`/`source` 等由 M1 填充）。**以本文档为契约，代码实现必须对齐。**

## 5. 精度递进说明（MVP → 迭代）

| 字段 | MVP（低精度） | 迭代阶段 B |
|------|--------------|-----------|
| 车型/人物识别 | YOLO 基础检测 | 多类别校准 + 融合 |
| 轨迹 | 中心点 + 时间戳（抽帧） | 多目标追踪 + 速度/加速度重建 |
| 碰撞点/事件 | 框重叠/速度骤变近似 | 精细碰撞重建 |
| 路况/信号灯 | 手动/规则/留空 | 语义识别 |

> 原则：**字段齐全（功能完整），数值可低置信（精度递进）**。任何未知字段填 `unknown` / 空数组，不删字段。
