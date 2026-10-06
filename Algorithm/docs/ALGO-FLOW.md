# RoadMind · 算法运作流程（ALGO-FLOW · P3）

> 版本：v1.0（2026-10-04）
> 范围：P3 算法部分的完整运作流程，从输入到输出。
> 配套：`EXECUTION-PLAN.md`（方案）、`SCENE-SCHEMA.md`（契约）、代码 `roadmind/backend/`

---

## 1. 整体流程

```
┌─ 输入 ─────────────────────────────────────────────┐
│  视频 / 照片 / 文字描述                              │
└─────────────────┬───────────────────────────────────┘
                  ▼
┌─ M1 视频感知 ──────────────────────────────────────┐
│  ① ultralytics model.track(bytetrack) 检测+追踪    │
│  ② 按 track_id 去重，提取轨迹点(t,x,y,w,h)          │
│  ③ 生成 scene（vehicles + 空事件）                  │
└─────────────────┬───────────────────────────────────┘
                  ▼
┌─ 碰撞事件识别 ─────────────────────────────────────┐
│  ④ 两两轨迹时间重叠段计算中心距离                   │
│  ⑤ 距离<0.08 → collision / near_miss              │
│  ⑥ 记录 participants(涉事目标id) + 时间            │
│  ⑦ 写回 scene.events                               │
└─────────────────┬───────────────────────────────────┘
                  ▼
┌─ M3 责任判定 ──────────────────────────────────────┐
│  ⑧ scene事件+目标类型 → 判责任                     │
│     · 含行人 → 机动车主责 80/20                     │
│     · 含非机动车 → 机动车主责 70/30                 │
│  ⑨ 无 scene 事件 → 文字关键词兜底                  │
│  ⑩ 输出 judgment（责任+依据+理由+置信度）           │
└─────────────────┬───────────────────────────────────┘
                  ▼
┌─ M4 应急方案 ──────────────────────────────────────┐
│  ⑪ 涉及行人 → 优先级1（急救/报警/保护现场）         │
│  ⑫ 普通碰撞 → 优先级2（双闪/三角牌/撤离）           │
│  ⑬ 输出 response（分步处置+保险指引）               │
└─────────────────┬───────────────────────────────────┘
                  ▼
        scene.json + judgment.json + response.json
```

---

## 2. 各步骤详解

### 2.1 检测+追踪（M1）
- 工具：`ultralytics.model.track(tracker="bytetrack.yaml")`
- 逻辑：逐帧检测 → ByteTrack 关联跨帧 ID → 同类目标投票定类
- 输出：`vehicles[{id, type, trajectory[]}]`，`trajectory` 每秒采样一个点

### 2.2 碰撞事件识别
- 对每两目标轨迹，在时间重叠段（|Δt|≤0.5s）找最小归一化中心距离
- 距离 < 0.08 且两框重叠 → `collision`；否则接近 → `near_miss`
- 记录 `participants=[id1, id2]`、`time`、`confidence`

### 2.3 责任判定（M3）
- 输入：scene 事件 + 参与者目标类型
- 规则：
  - 含 `pedestrian` → 机动车主责 80/20（道交法47条）
  - 含 `motorcycle/bicycle` → 机动车主责 70/30
- 无碰撞事件 → 用文字关键词兜底规则

### 2.4 应急方案（M4）
- 涉及行人 → 优先级 1：双闪、120、122/110、三角牌、护现场
- 普通碰撞 → 优先级 2：双闪、三角牌、撤离

---

## 3. 代码 → 流程映射

| 流程步骤 | 代码文件 |
|----------|---------|
| ①-③ 检测+追踪→scene | `scripts/full_pipeline.py` / `app/services/video_tracker.py` / `my_scene.py` |
| ④-⑦ 碰撞识别 | `app/collision.py` |
| ⑧-⑩ 责任判定 | `app/services/rule_judge.py` |
| ⑨ 场景摘要 | `app/services/scene_summary.py` |
| ⑪-⑬ 应急方案 | `full_pipeline` 内 `draft_response` |

---

## 4. 一键运行（算法验证）

```bash
cd roadmind/backend
python scripts/full_pipeline.py --source test2.mp4 --model yolov8s.pt \
    --conf 0.3 --iou 0.6 --out ./data/outputs
```

输出：`scene.json` + `judgment.json` + `response.json`

---

## 5. 验证脚本（算法质量）

| 脚本 | 验证内容 | 状态 |
|------|----------|:---:|
| `test_event_detect.py` | 碰撞事件识别 | ✅ |
| `test_judge_scene.py` | 场景数据判责 | ✅ |
| `test_full_pipeline_logic.py` | 全链路判责+应急 | ✅ |
