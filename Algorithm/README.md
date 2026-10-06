# Algorithm · 算法模块（P3）

> 独立算法模块，从 `roadmind/` 复制而来，解耦于后端/前端。
> 你负责的算法部分集中于此，可独立运行与验证。

## 目录结构

```
Algorithm/
├── core/            # 算法核心（纯函数，无第三方依赖）
│   ├── collision.py          # 碰撞事件识别
│   ├── rule_judge.py         # 责任判定规则
│   ├── scene_summary.py      # 场景摘要
│   └── video_tracker.py      # 检测+追踪（ultralytics 原生）
├── scripts/         # 算法脚本
│   ├── full_pipeline.py      # 全链路：视频→scene→判责→应急
│   ├── convert_to_scene.py   # 视频 → scene.json
│   └── detect_count.py       # 去重计数调试
├── tests/           # 算法验证
│   ├── test_event_detect.py
│   ├── test_judge_scene.py
│   └── test_full_pipeline_logic.py
└── docs/            # 算法文档
    ├── SCENE-SCHEMA.md
    ├── ALGO-FLOW.md
    └── EXECUTION-PLAN.md
```

## 全链路运行（需 ultralytics 环境）

```bash
cd Algorithm/scripts
python full_pipeline.py --source test2.mp4 --model yolov8s.pt --out ./data/outputs
```

## 验证（纯逻辑，无需第三方包）

```bash
cd Algorithm/tests
python test_event_detect.py
python test_judge_scene.py
python test_full_pipeline_logic.py
```

> 说明：`core/` 与 `tests/` 为纯逻辑（无 app 依赖），可在任意 Python 运行；
> `scripts/` 中需要 ultralytics 的脚本在装有 YOLO 的环境运行。
> 原实现位于 `../roadmind/`，本目录为副本（改动请回写到 roadmind 保持同步）。
