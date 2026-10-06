"""
YOLO + ByteTrack 检测与去重计数脚本（调参版，专注解决重复计数）。

特点：
- conf 过滤低置信假框
- iou 调大抑制同一目标的多个重叠框（重复计数主因之一）
- 按 tracker_id 去重统计「唯一目标数」，避免同一目标重复计数
- 保存：检测框可视化视频 + 按 tracker_id 统计的轨迹/计数

用法：
    python detect_count.py --video 视频.mp4 --model yolov8s.pt \
        --conf 0.35 --iou 0.5 --lost-buffer 60

参数说明（针对重复计数）：
    --conf   检测置信度阈值（低则噪声多，高则漏检）
    --iou    NMS 阈值（调大抑制重叠重复框，建议 0.45~0.6）
    --lost-buffer  目标消失多少帧仍保留原ID（调大减少ID跳变）
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

# YOLOv8 COCO 类别 → 名称
_CLS_NAME = {0: "person", 1: "bicycle", 2: "car", 3: "motorcycle",
             5: "bus", 7: "truck"}


def main(video_path: str, model_name: str, out_dir: str,
         conf: float, iou: float, imgsz: int, frame_step: int,
         lost_buffer: int, activation_threshold: float) -> None:
    from ultralytics import YOLO
    from supervision import ByteTrack, Detections

    model = YOLO(model_name)

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    tracker = ByteTrack(
        track_activation_threshold=activation_threshold,
        lost_track_buffer=lost_buffer,
        frame_rate=fps,
    )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(out_dir / "tracked.mp4"),
        cv2.VideoWriter_fourcc(*"mp4v"), fps,
        (int(cap.get(3)), int(cap.get(4))),
    )

    # track_id -> {type, count, first_seen}
    uniques: dict[int, dict] = {}
    frame_idx = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if frame_idx % frame_step != 0:
            frame_idx += 1
            continue

        results = model(frame, conf=conf, iou=iou, imgsz=imgsz, verbose=False)[0]
        det = results.boxes
        boxes = det.xyxy.numpy() if det is not None else np.empty((0, 4))
        confs = det.conf.numpy() if det is not None else np.empty(0)
        clss = det.cls.numpy() if det is not None else np.empty(0)

        detections = Detections(xyxy=boxes, confidence=confs, class_id=clss.astype(int))
        detections = tracker.update_with_detections(detections)

        for det in detections:
            tid = int(det.tracker_id)
            x1, y1, x2, y2 = det.xyxy
            cls = int(det.class_id)
            c = float(det.confidence)

            if tid not in uniques:
                uniques[tid] = {"type": _CLS_NAME.get(cls, "?"), "count": 0, "first": frame_idx}
            uniques[tid]["count"] += 1

            # 画框 + 唯一ID
            color = (0, 200, 0) if cls in (2, 5, 7) else (0, 0, 255)
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            cv2.putText(frame, f"#{tid} {_CLS_NAME.get(cls,'?')} {c:.2f}",
                        (int(x1), int(y1) - 6), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, color, 1)

        writer.write(frame)
        frame_idx += 1

    cap.release()
    writer.release()

    # 统计结果：按类别统计唯一目标数
    by_type: dict[str, int] = defaultdict(int)
    for info in uniques.values():
        by_type[info["type"]] += 1

    print("=" * 50)
    print(f"轨迹总数（track_id 去重）: {len(uniques)}")
    print("按类别唯一目标数:")
    for t, n in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t:<10}: {n}")
    print("=" * 50)
    print(f"可视化视频 -> {out_dir / 'tracked.mp4'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, help="视频路径")
    ap.add_argument("--model", default="yolov8s.pt", help="YOLO 权重")
    ap.add_argument("--out", default="./data/outputs", help="输出目录")
    ap.add_argument("--conf", type=float, default=0.35, help="检测置信度")
    ap.add_argument("--iou", type=float, default=0.5, help="NMS IoU（调大抑制重复框）")
    ap.add_argument("--imgsz", type=int, default=640, help="输入尺寸")
    ap.add_argument("--frame-step", type=int, default=1, help="抽帧间隔")
    ap.add_argument("--lost-buffer", type=int, default=60, help="丢失保留帧数")
    ap.add_argument("--activation-threshold", type=float, default=0.25, help="新建轨迹阈值")
    args = ap.parse_args()

    main(args.video, args.model, args.out,
         args.conf, args.iou, args.imgsz, args.frame_step,
         args.lost_buffer, args.activation_threshold)
