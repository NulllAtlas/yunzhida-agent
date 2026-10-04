"""
视频感知核心模块（M1·真实检测）。

封装 YOLO + ByteTrack 的检测与追踪逻辑，输出符合 SCENE-SCHEMA 的 Scene 对象，
并支持关键帧提取。供 byte_track_demo.py 与 perception.py 服务共用。

依赖：ultralytics, supervision, opencv-python
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from typing import TYPE_CHECKING

from app.collision import detect_events_from_tracks

if TYPE_CHECKING:
    from app.schemas.models import Scene, TrajectoryPoint, Vehicle


class VideoPerceiver:
    """对一段视频执行 抽帧→检测→追踪，生成轨迹 + 关键帧。"""

    def __init__(
        self,
        model_name: str = "yolov8s.pt",
        conf: float = 0.25,
        iou: float = 0.5,
        imgsz: int = 640,
        frame_step: int = 1,
        track_activation_threshold: float = 0.25,
        lost_track_buffer: int = 30,
    ):
        self._conf = conf
        self._iou = iou
        self._imgsz = imgsz
        self._frame_step = frame_step
        self._track_activation_threshold = track_activation_threshold
        self._lost_track_buffer = lost_track_buffer

        # 延迟导入，避免未装 CV 依赖时影响纯 mock 流程
        from ultralytics import YOLO

        self._model = YOLO(model_name)

    def _new_tracker(self, fps: float):
        from supervision import ByteTrack

        return ByteTrack(
            track_activation_threshold=self._track_activation_threshold,
            lost_track_buffer=self._lost_track_buffer,
            frame_rate=fps,
        )

    def perceive(self, video_path: str, scene_id: str) -> "tuple[Scene, list[tuple[float, np.ndarray]]]":
        """返回 (Scene, [(时间, 关键帧图), ...])。"""
        from app.schemas.models import Scene, TrajectoryPoint, Vehicle  # noqa: F401
        from supervision import Detections

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        tracker = self._new_tracker(fps)

        frame_idx = 0
        tracks: dict[int, dict] = {}
        keyframes: list[tuple[float, np.ndarray]] = []

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_idx % self._frame_step != 0:
                frame_idx += 1
                continue

            results = self._model(frame, conf=self._conf, iou=self._iou,
                                  imgsz=self._imgsz, verbose=False)[0]
            det = results.boxes
            boxes = det.xyxy.numpy() if det is not None else np.empty((0, 4))
            confs = det.conf.numpy() if det is not None else np.empty(0)
            clss = det.cls.numpy() if det is not None else np.empty(0)

            detections = Detections(xyxy=boxes, confidence=confs, class_id=clss.astype(int))
            detections = tracker.update_with_detections(detections)

            h, w = frame.shape[:2]
            t = frame_idx / fps

            # 关键帧：检测到目标数>0 且含高置信框时保存（MVP：每 N 帧存一帧）
            if len(detections) > 0:
                keyframes.append((t, frame.copy()))

            for det in detections:
                tid = int(det.tracker_id)
                x1, y1, x2, y2 = det.xyxy
                cls = int(det.class_id)
                cx = ((x1 + x2) / 2) / w
                cy = ((y1 + y2) / 2) / h
                if tid not in tracks:
                    tracks[tid] = {"points": [], "type": _CLS_TO_TYPE.get(cls, "other")}
                tracks[tid]["points"].append(
                    TrajectoryPoint(t=t, x=cx, y=cy, w=(x2 - x1) / w, h=(y2 - y1) / h)
                )
            frame_idx += 1

        cap.release()

        vehicles: list[Vehicle] = []
        for tid, info in tracks.items():
            pts = info["points"]
            max_speed = 0.0
            if len(pts) >= 2:
                dx = pts[-1].x - pts[0].x
                dt = pts[-1].t - pts[0].t
                if dt > 0:
                    max_speed = abs(dx) / dt * 100.0
            vehicles.append(Vehicle(id=tid, type=info["type"],
                                    trajectory=pts, max_speed_kmh=round(max_speed, 1)))

        # D3：碰撞事件识别（基于轨迹后处理）
        events = self._detect_collision_events(tracks)

        scene = Scene(
            scene_id=scene_id,
            source="video",
            vehicles=vehicles,
            events=events,
            confidence=0.5,  # 低精度 MVP
        )
        return scene, keyframes

    @staticmethod
    def _detect_collision_events(self, tracks: dict[int, dict]) -> "list":
        """碰撞事件识别（基于轨迹后处理）。"""
        from app.schemas.models import SceneEvent  # noqa: F401

        raw = detect_events_from_tracks({
            tid: {"points": [{"t": p.t, "x": p.x, "y": p.y, "w": p.w, "h": p.h}
                             for p in info["points"]]}
            for tid, info in tracks.items()
        })
        return [SceneEvent(**e) for e in raw]

    def save_keyframes(self, keyframes: list[tuple[float, np.ndarray]], out_dir: Path) -> list[str]:
        """保存关键帧，返回文件路径列表。"""
        out_dir.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        for i, (t, frame) in enumerate(keyframes):
            p = out_dir / f"kf_{i:04d}_t{t:.2f}.jpg"
            cv2.imwrite(str(p), frame)
            paths.append(str(p))
        return paths
