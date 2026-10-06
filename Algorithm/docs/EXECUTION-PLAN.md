# RoadMind · 算法部分执行方案（EXECUTION PLAN · P3）

> 版本：v1.0（2026-10-04，与代码实现同步）
> 作者：P3（算法/核心智能）
> 范围：本文件只描述**算法部分**（M1 视频感知、M3 责任判定、M4 应急、M2 规则数据）。
> 其他（后端编排/前端/PPT）不在本文件范围。

---

## 1. 算法部分职责

| 编号 | 模块 | 一句话 |
|------|------|--------|
| M1 | 视频感知 | 视频 → 检测目标 → 生成 scene（轨迹/事件） |
| M2 | 规则数据 | 法条 + 案例整理（配合 P1），供 RAG/判责 |
| M3 | 责任判定 | scene 数据 → 责任认定建议 |
| M4 | 应急方案 | 事故类型 → 处置步骤 |

## 2. 算法数据流

```
视频 → M1 检测+追踪 → scene.json → 碰撞事件识别
     → 场景摘要 → M3 责任判定 → judgment.json
     → M4 应急方案 → response.json
```

## 3. 已实现（算法侧）

| 文件 | 模块/作用 | 状态 |
|------|----------|:---:|
| `roadmind/backend/docs/SCENE-SCHEMA.md` | scene 契约 | ✅ |
| `roadmind/backend/app/collision.py` | 碰撞事件识别（纯函数） | ✅ |
| `roadmind/backend/app/services/scene_summary.py` | 场景→判责文本 | ✅ |
| `roadmind/backend/app/services/rule_judge.py` | 场景驱动判责规则 | ✅ |
| `roadmind/backend/app/services/video_tracker.py` | 检测+追踪（ultralytics 原生） | ✅ |
| `roadmind/backend/scripts/full_pipeline.py` | 视频→scene→判责→应急 | ✅ |
| `roadmind/backend/scripts/test_*.py` | 事件/判责/全链路验证 | ✅ |

## 4. 算法核心流程说明

### 4.1 检测+追踪（M1）
- 使用 `ultralytics model.track(tracker="bytetrack.yaml")`（与你实测一致）
- 输出 `scene.json`：vehicles（trace_id 去重 + 轨迹点）+ events

### 4.2 碰撞事件识别（collision.py）
- 轨迹中心距离 < 0.08 且时间重叠 → collision / near_miss
- 记录 participants（涉事目标 id）

### 4.3 责任判定（rule_judge.py）
- 优先基于 scene events/目标类型判责（车撞行人 80/20、非机动车 70/30 等）
- 无场景数据时文字关键词兜底

### 4.4 应急方案（full_pipeline 内 draft_response）
- 涉及行人优先级 1（急救/报警/保护现场），普通碰撞优先级 2

## 5. 里程碑（算法）

| 里程碑 | 验收 | 状态 |
|--------|------|:---:|
| D1 检测跑通 | YOLO 检测出目标 | ✅ |
| D2 检测→scene | 视频 → scene.json | ✅ |
| D3 事件+判责 | 碰撞识别 + 场景判责 | ✅ |
| D8+ 精度优化 | 感知/判责精度提升（迭代） | ⏳ |

## 6. 已知待优化（迭代阶段 B，算法侧）

- 视频感知精度：多车轨迹重建、夜间/遮挡、bus/truck 类别纠错、车上人员关联
- 判责质量：接入真实 LLM、更大法条库、置信评估

## 7. 运行（算法验证）

```bash
cd roadmind/backend
python scripts/full_pipeline.py --source test2.mp4 --model yolov8s.pt --out ./data/outputs
```
