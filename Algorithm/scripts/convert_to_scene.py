"""
检测 → scene.json 转换脚本（基于 YOLO model.track + ByteTrack）。

作用：把视频检测追踪结果转换为符合 SCENE-SCHEMA（roadmind/backend/docs/SCENE-SCHEMA.md）
的 Scene JSON 输出，供责任判定(M3)/应急(M4) 与后端 perception 服务消费。

依赖：ultralytics（自带 bytetrack，无需 supervision）
用法：
    python convert_to_scene.py --source test2.mp4 --model yolov8s.pt \
        --out ./data/outputs --scene-id case_001

说明：
- 目标按 track_id 归类（解决重复计数）
- 每秒采样轨迹点（避免 JSON 过大）
- 按类别输出唯一目标计数
- 可选保存关键帧图
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from ultralytics import YOLO

# COCO 类别 → RoadMind Scene.type
_CLS_TO_SCENE_TYPE = {
    "person": "pedestrian",
    "bicycle": "bicycle",
    "car": "car",
    "motorcycle": "motorcycle",
    "bus": "bus",
    "truck": "truck",
    "train": "other",
}


def main(source: str, model_name: str, out_dir: str,
         scene_id: str, conf: float, iou: float,
         sample_interval: float = 1.0, save_keyframes: bool = False) -> None:
    model = YOLO(model_name)

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # track_id -> {"type", "trajectory": [(t, x, y, w, h)]}
    tracks: dict[int, dict] = {}
    track_class_votes: dict[int, Counter] = {}
    keyframes = []
    fps = None

    for result in model.track(
        source=source,
        tracker="bytetrack.yaml",
        persist=True,
        conf=conf,
        iou=iou,
        verbose=True,
        stream=True,
    ):
        if fps is None:
            fps = result.speed  # not fps; 下面用 result 的 frame 时间处理
        boxes = result.boxes
        if boxes.id is None:
            continue

        frame_w, frame_h = (result.orig_shape[1], result.orig_shape[0])
        img = result.orig_img
        frame_t = len(keyframes)  # 简化：按处理帧序号近似时间

        for cls_id, track_id, xyxy in zip(
            boxes.cls.tolist(), boxes.id.tolist(), boxes.xyxy.tolist()
        ):
            cls_name = model.names[int(cls_id)]
            track_id = int(track_id)
            track_class_votes.setdefault(track_id, Counter())[cls_name] += 1

            x1, y1, x2, y2 = xyxy
            cx = ((x1 + x2) / 2) / frame_w
            cy = ((y1 + y2) / 2) / frame_h
            w = (x2 - x1) / frame_w
            h = (y2 - y1) / frame_h

            td = tracks.setdefault(track_id, {"type": cls_name, "trajectory": []})
            # 采样：同一 track 每秒至多记录一个点
            if not td["trajectory"] or frame_t - td["trajectory"][-1]["t"] >= sample_interval:
                td["trajectory"].append({"t": frame_t, "x": cx, "y": cy, "w": w, "h": h})

        if save_keyframes and len(result.boxes) and len(result.boxes) > 0:
            keyframes.append((frame_t, img))

    # 确定每个 track 的最终类型（多数投票，避免类别抖动）
    track_type = {
        tid: votes.most_common(1)[0][0] for tid, votes in track_class_votes.items()
    }

    # 组装 Scene JSON 结构
    vehicles = []
    for tid, td in tracks.items():
        cls_name = track_type.get(tid, td["type"])
        stype = _CLS_TO_SCENE_TYPE.get(cls_name, "other")
        pts = td["trajectory"]
        max_speed = 0.0
        if len(pts) >= 2 and pts[-1]["t"] - pts[0]["t"] > 0:
            # 归一化位移/时间 → 参考速度（MVP 示意值）
            max_speed = abs(pts[-1]["x"] - pts[0]["x"]) / (pts[-1]["t"] - pts[0]["t"]) * 100.0
        vehicles.append({
            "id": tid,
            "type": stype,
            "trajectory": pts,
            "max_speed_kmh": round(max_speed, 1),
        })

    scene = {
        "$schema": "scene.v1.json",
        "scene_id": scene_id,
        "source": "video",
        "vehicles": vehicles,
        "events": [],  # 碰撞/关键事件识别留待 D3
        "road": "unknown",
        "lane_markings": "unknown",
        "traffic_light": "unknown",
        "visibility": "unknown",
        "confidence": 0.5,  # 低精度 MVP
    }

    json_path = out / f"{scene_id}.scene.json"
    import json
    json_path.write_text(json.dumps(scene, ensure_ascii=False, indent=2), encoding="utf-8")

    # 统计
    track_counts = Counter(track_type.values())
    print("=" * 50)
    print(f"scene.json -> {json_path}")
    print(f"轨迹总数（track_id 去重）: {len(vehicles)}")
    print("按类别唯一目标数:")
    for cls_name, n in sorted(track_counts.items(), key=lambda x: -x[1]):
        stype = _CLS_TO_SCENE_TYPE.get(cls_name, "other")
        print(f"  {cls_name:<10}({stype}): {n}")
    print("=" * 50)

    if keyframes and save_keyframes:
        kf_dir = out / "keyframes"
        kf_dir.mkdir(parents=True, exist_ok=True)
        import cv2
        for i, (t, img) in enumerate(keyframes):
            cv2.imwrite(str(kf_dir / f"{scene_id}_t{t}.jpg"), img)
        print(f"关键帧 -> {kf_dir}/")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="视频/图像路径")
    ap.add_argument("--model", default="yolov8s.pt", help="YOLO 权重")
    ap.add_argument("--out", default="./data/outputs", help="输出目录")
    ap.add_argument("--scene-id", default="case", help="scene_id")
    ap.add_argument("--conf", type=float, default=0.35, help="检测置信度")
    ap.add_argument("--iou", type=float, default=0.5, help="NMS IoU")
    ap.add_argument("--sample-interval", type=float, default=1.0, help="轨迹采样间隔(秒)")
    ap.add_argument("--save-keyframes", action="store_true", help="是否保存关键帧")
    args = ap.parse_args()

    main(args.source, args.model, args.out, args.scene_id,
         args.conf, args.iou, args.sample_interval, args.save_keyframes)
