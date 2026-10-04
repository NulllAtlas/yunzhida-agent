"""
ByteTrack 追踪起步脚本（D1 · 检测→追踪 demo）。

用 supervision 库的 ByteTrack 包装器，配合 ultralytics YOLO：
帧 → 检测框 → ByteTrack 追踪 → 输出 scene.json（轨迹点）+ 可视化结果视频/图。

依赖：pip install ultralytics supervision

用法：
    python byte_track_demo.py --video 路径/视频.mp4 --model yolov8n.pt
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def _make_models():
    """延迟导入 app 与 ultralytics，保证脚本可独立运行（不依赖 app 路径/当前环境）。"""
    from ultralytics import YOLO
    from app.schemas.models import Scene, SceneEvent, TrajectoryPoint, Vehicle
    return YOLO, Scene, SceneEvent, TrajectoryPoint, Vehicle


def main(
    video_path: str,
    model_name: str,
    out_dir: str,
    conf: float = 0.25,
    iou: float = 0.5,
    imgsz: int = 640,
    frame_step: int = 1,
    track_activation_threshold: float = 0.25,
    lost_track_buffer: int = 30,
) -> None:
    from supervision import ByteTrack, Detections

    model = YOLO(model_name)

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    tracker = ByteTrack(
        track_activation_threshold=track_activation_threshold,
        lost_track_buffer=lost_track_buffer,
        frame_rate=fps,
    )
    frame_idx = 0

    # 轨迹缓存：track_id -> {t: x, y}
    tracks: dict[int, dict] = {}
    vehicles: dict[int, Vehicle] = {}
    events: list[SceneEvent] = []

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(out_dir / "tracked.mp4"),
        cv2.VideoWriter_fourcc(*"mp4v"), fps,
        (int(cap.get(3)), int(cap.get(4))),
    )

    # 类别名：YOLOv8 COCO 中 person=0, car=2, bicycle=1, motorcycle=3, truck=7, bus=5
    cls_to_type = {0: "pedestrian", 1: "bicycle", 2: "car", 3: "motorcycle",
                   5: "bus", 7: "truck"}

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        # 抽帧处理：每 frame_step 帧处理一次（frame_step=1 全帧）
        if frame_idx % frame_step != 0:
            frame_idx += 1
            continue
        results = model(frame, conf=conf, iou=iou, imgsz=imgsz, verbose=False)[0]
        det = results.boxes

        boxes = det.xyxy.numpy() if det is not None else np.empty((0, 4))
        confs = det.conf.numpy() if det is not None else np.empty(0)
        clss = det.cls.numpy() if det is not None else np.empty(0)

        detections = Detections(
            xyxy=boxes,
            confidence=confs,
            class_id=clss.astype(int),
        )
        detections = tracker.update_with_detections(detections)

        h, w = frame.shape[:2]
        t = frame_idx / fps

        for det in detections:
            track_id = int(det.tracker_id)
            x1, y1, x2, y2 = det.xyxy
            cls = int(det.class_id)
            conf = float(det.confidence)

            cx = ((x1 + x2) / 2) / w
            cy = ((y1 + y2) / 2) / h

            if track_id not in tracks:
                tracks[track_id] = {"points": [], "type": cls_to_type.get(cls, "other")}
            tracks[track_id]["points"].append(TrajectoryPoint(t=t, x=cx, y=cy,
                                                              w=(x2 - x1) / w,
                                                              h=(y2 - y1) / h))

            # 画框
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
            cv2.putText(frame, f"#{track_id} {cls_to_type.get(cls,'?')} {conf:.2f}",
                        (int(x1), int(y1) - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (0, 255, 0), 1)

        writer.write(frame)
        frame_idx += 1

    cap.release()
    writer.release()

    # 组装 scene（MVP：只有轨迹，事件/路况留待后续）
    for tid, info in tracks.items():
        pts = info["points"]
        max_speed = 0.0
        if len(pts) >= 2:
            # 粗略速度估算（像素/秒 → 简化 kmh，MVP 参考值）
            dx = pts[-1].x - pts[0].x
            dt = pts[-1].t - pts[0].t
            if dt > 0:
                max_speed = abs(dx) / dt * 100.0
        vehicles[tid] = Vehicle(id=tid, type=info["type"],
                                trajectory=pts, max_speed_kmh=round(max_speed, 1))

    scene = Scene(
        scene_id=Path(video_path).stem,
        source="video",
        vehicles=list(vehicles.values()),
        events=events,
        confidence=0.5,  # 低精度 MVP
    )

    out_json = out_dir / "scene.json"
    out_json.write_text(scene.model_dump_json(indent=2), encoding="utf-8")
    print(f"scene.json -> {out_json}")
    print(f"tracked.mp4  -> {out_dir / 'tracked.mp4'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="YOLO + ByteTrack 追踪 demo，输出 scene.json")
    ap.add_argument("--video", required=True, help="行车记录仪视频路径")
    ap.add_argument("--model", default="yolov8n.pt", help="YOLO 权重")
    ap.add_argument("--out", default="./data/outputs", help="输出目录")
    ap.add_argument("--conf", type=float, default=0.25, help="检测置信度阈值（调重复计数用）")
    ap.add_argument("--iou", type=float, default=0.5, help="NMS IoU 阈值")
    ap.add_argument("--imgsz", type=int, default=640, help="检测输入尺寸")
    ap.add_argument("--frame-step", type=int, default=1, help="抽帧间隔（1=全帧）")
    ap.add_argument("--track-thresh", type=float, default=0.25,
                    help="ByteTrack 新建轨迹置信阈值")
    ap.add_argument("--lost-buffer", type=int, default=30,
                    help="ByteTrack 丢失目标保留缓冲帧数（遮挡/漏检调大）")
    args = ap.parse_args()
    main(
        args.video,
        args.model,
        args.out,
        conf=args.conf,
        iou=args.iou,
        imgsz=args.imgsz,
        frame_step=args.frame_step,
        track_activation_threshold=args.track_thresh,
        lost_track_buffer=args.lost_buffer,
    )
