# SCENE-SCHEMA.md · scene.json 结构 v4.1（同步 backend/app/schemas/models.py）

> 版本：v4.1（2026-10-06，与 `backend/app/schemas/models.py` + `app/algo/video_tracker.py`
> + `app/algo/photo_detector.py` + `app/services/text_facts.py` 对齐）
> 感知模块（M1）输出，供判定（M3）、应急（M4）、前端（M6）消费。

## scene.json 结构

```json
{
  "scene_id": "case_adf72a071510",
  "source": "video",
  "vehicles": [
    {
      "id": 1,
      "type": "car",
      "trajectory": [{ "t": 0.0, "x": 0.5, "y": 0.7, "speed_kmh": 0.0 }],
      "max_speed_kmh": 40.0
    }
  ],
  "events": [
    {
      "time": 1.93,
      "type": "collision",
      "participants": [59, 70],
      "confidence": 0.79,
      "keyframe": null,
      "geometry": "crossing"
    }
  ],
  "photos": [
    {
      "name": "adf72a071510_p0.jpg",
      "width": 1280,
      "height": 720,
      "targets": [
        { "type": "car", "confidence": 0.88, "bbox": [0.31, 0.42, 0.22, 0.19] },
        { "type": "pedestrian", "confidence": 0.61, "bbox": [0.66, 0.38, 0.08, 0.22] }
      ],
      "traffic_light": "red",
      "note": "静态画面（单帧），无法判断运动速度与方向（照片仅能佐证现场目标与信号灯状态）"
    }
  ],
  "text_facts": {
    "raw": "我车直行是绿灯，对方闯红灯左转，路口有禁止左转标志",
    "my_light": "green",
    "other_light": "red",
    "red_light_violation": "yes",
    "red_light_by": "other",
    "signs": ["禁止左转"],
    "violations": [],
    "matched": ["绿灯", "红灯", "闯红灯", "禁止左转"]
  },
  "traffic_lights": [
    { "id": 3, "state": "red", "x": 0.1792, "y": 0.1908 },
    { "id": 6, "state": "green", "x": 0.3903, "y": 0.1902 }
  ],
  "road": "unknown",
  "lane_markings": "unknown",
  "traffic_light": "mixed",
  "visibility": "unknown",
  "confidence": 0.5
}
```

## 字段说明

| 字段 | 说明 |
| --- | --- |
| `source` | 来源：`video`（真实视频检测）/ `photo`（**现场照片单帧检测**）/ `text`（文字输入）/ `text_fallback`（**传了视频但检测失败，已降级为文字推断**）/ `mock` |
| `vehicles[].type` | `car` / `truck` / `motorcycle` / `bicycle` / `pedestrian` / `other` |
| `vehicles[].trajectory` | 时间序列：时间 t(s)、归一化坐标 x/y(0-1)、速度 speed_kmh |
| `vehicles[].max_speed_kmh` | 轨迹峰值速度。**注意**：归一化坐标无法换算真实车速，此值是相对量纲的代理指标，仅供 `judge._accident_gate` 阈值比较 |
| `events[].type` | 视频来源只会产出 `collision` / `near_miss`；文字降级场景才可能带语义类型（`rear_end` / `vehicle_pedestrian`） |
| `events[].confidence` | 事件置信度 = `1 - 最近距离×10`，低于 `min_confidence`（0.5）的事件已被丢弃 |
| `events[].geometry` | 碰撞形态：`same_direction`（同向/追尾）/ `crossing`（交叉/路口侧碰）/ `oblique` / `unknown`（至少一方静止或轨迹不足） |
| `photos[]` | 随附现场照片的单帧检测证据，见下节。没交照片时为空数组 |
| `text_facts` | 从用户补充文字里提取的现场要素（**用户陈述**，不是检测结果），见下节。没提取到东西时为 `null` |
| `traffic_lights[]` | 逐灯颜色，见下 |
| `traffic_light` | 汇总：`red` / `green` / `yellow` / `mixed` / `unknown`；照片场景取各照片判色的汇总 |
| `road` / `lane_markings` / `visibility` | 道路交通场景要素，**当前恒为 `unknown`**（未实现识别） |
| `confidence` | 场景置信度 0-1，低则触发补录；照片场景按视频置信度打 **0.6 折扣**（静态证据弱于运动学证据） |

## 现场照片证据（photos）

用户可以在提交视频之外**另附现场照片**（也可以只交照片 + 文字描述）。照片走独立单帧检测
（`app/algo/photo_detector.py`，`model.predict` + 复用信号灯 HSV 判色），产出：

| 字段 | 说明 |
| --- | --- |
| `name` | 落盘存储名（`{task_id}_p{i}{suffix}`），**不回显原图**，仅供追溯 |
| `targets[].type` | 与 `vehicles[].type` 同一套映射；**信号灯/停止标志不进 targets**（场景要素不参与判责） |
| `targets[].bbox` | 归一化 `[x, y, w, h]`，左上角 + 宽高，取值 0-1 |
| `traffic_light` | 该照片内信号灯的 HSV 判色汇总：`red` / `green` / `yellow` / `mixed` / `unknown` |
| `note` | **局限说明**，原样进判定 prompt |

三条硬约束：

1. **照片是静态单帧**：`detect_events` 要求轨迹 ≥2 个采样点，单帧必然得不出速度与碰撞事件，
   因此 `note` 固定标注「静态画面（单帧），无法判断运动速度与方向」。
2. **照片不进事故门控**：`judge._accident_gate` 依赖 `vehicles[].max_speed_kmh` 与碰撞事件置信度，
   只有 `source=="video"` 的来源才够资格。照片证据只进判定上下文（prompt），
   避免把静态画面当成"已确认事故"。
3. **不编造**：mock 模式、图片读不出、模型不可用等情况下，`targets` 一律留空，
   只在 `note` 里说明原因 —— 与视频降级路径同一原则。

照片证据经 `app/algo/scene_summary.py::describe_photos` 渲染成文本进判定与应急 prompt；
用户文字描述与场景证据是**两份独立输入，合并后同时进 prompt**（不再二选一）。

## 用户陈述（text_facts）

视频/照片认不出的现场要素由用户的补充描述来补：**信号灯归属**（多方向灯并存时检测只能给
`mixed`，无法把车辆关联到具体信号灯）、**路口指示牌**、**其他过错关键词**。
`services/text_facts.py` 按关键词规则抽成 `TextFacts` 随场景一起流动。

| 字段 | 说明 |
| --- | --- |
| `raw` | 用户原话（截断 200 字），便于追溯 |
| `my_light` / `other_light` | 用户陈述的双方方向信号灯：`red` / `green` / `yellow` / `unknown` |
| `red_light_violation` / `red_light_by` | 是否指认闯红灯（`yes`）以及是谁（`self` / `other`） |
| `signs[]` | 提到的路口指示牌 / 标志 / 标线（禁止左转、让行、限速、斑马线…） |
| `violations[]` | 其他过错关键词（压实线、逆行、超速、闯黄灯…） |
| `matched[]` | 命中的原词，便于人工核对 |

三条纪律（判定提示词 `services/llm.py::_RULES_PROMPT` 与之对应）：

1. **不冒充检测结果**：渲染进 prompt 时统一带前缀
   「用户陈述（由补充文字关键词提取，未经检测验证；与检测结果冲突时以检测为准）」。
2. **不做过度归因**：没写"我方/对方"的裸"红灯"不塞给任何一方；光凭"某方是红灯"也不断言闯红灯
   （对方可能正停在路口等灯）—— 只有明写"闯红灯"、或两侧灯色明确相反（我方绿 + 对方红）才算指认。
3. **不越权判定**：提示词允许"检测为 `mixed` / 未识别时可依据用户陈述判红灯"，
   但要求 LLM 在 `reasoning` 里注明依据、并在 `confidence` 上体现不确定性；
   "闯黄灯 / 抢黄灯"不构成闯红灯（与 `RULES.md §3.4` 一致）。

最终结论仍由 LLM 统一辅助输出（`red_light_violation` 等）；规则兜底路径（mock 模式或
LLM 输出不可解析）读的是同一份 `TextFacts`，见 `llm.py::_rule_red_light`。

### 信号灯：为什么是逐灯 + 汇总

同一路口**不同方向的红绿灯同时存在**。实测一段路口视频能同时检出红灯(#3)与绿灯(#6)。

因此 `traffic_lights` 逐灯记录颜色，`traffic_light` 汇总：多色并存时取 **`mixed`**。

`mixed` 是给下游的**明确警告**：无法把车辆关联到具体信号灯，**不得据此判定某一方闯红灯**。
（`app/algo/scene_summary.py::describe_lights` 会把这句话写进给 LLM 的场景描述。）

## 事件过滤（过检抑制）

裸距离阈值在密集车流里会大量误报——实测一段正常路口视频能检出 22 个"碰撞"，
参与者还全是停着排队的车。`video_tracker.detect_events` 因此有五重过滤：

1. 双方轨迹点数均 ≤1：单帧闪烁的误检目标；
2. 双方均静止（位移 < 0.01）：静止目标之间物理上不可能碰撞；
3. 含信号灯/停止标志：场景要素而非交通参与者；
4. **全程贴合**（间距从未达到 `_MIN_APPROACH`=0.10）：碰撞必须意味着"接近"，
   从未分开过的是重复轨迹或 2D 投影长期重叠。**仅在共视采样点 ≥2 时生效**——
   点数不足时证据不够，退回自然判据（否则短轨迹会被无条件否决）；
5. 事件置信度 < `min_confidence`（0.5）。

时间配对容差 `_TIME_TOL`=0.3s：只在"同一时刻"比较，否则会拿 A 的旧位置比 B 的新位置。
容差必须小于半个采样周期（轨迹每 ~0.5s 取一点）。

> 已知残留：2D 画面的框重叠不等于物理碰撞。相邻车道、不同景深的两车在投影上也会重叠，
> 现有判据无法分辨，需要地面平面/3D 推理。

## 降级规则

- 传了视频但检测失败（文件不存在 / 无 ultralytics / 解析异常）→ `source="text_fallback"`，
  **vehicles/events 留空、不编造检测结果**，`judge` 会把置信度压到 ≤0.3 并在 reasoning 首条说明。
- 随附照片检测未运行 / 失败（mock 模式 / 图片读不出 / 无 ultralytics）→ 该张照片 `targets` 留空，
  `note` 写明原因；**不影响**同一次提交里的视频与文字证据。
- `confidence` 过低或 `vehicles` 为空 → 前端转**文字补录**，以 `text_description` 重新触发判定。
