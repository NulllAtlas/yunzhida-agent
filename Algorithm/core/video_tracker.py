"""
视频检测+追踪（M1·真实检测，ultralytics 原生 track 实现）。

与 scripts/full_pipeline.py 的核心逻辑一致，供 perception 服务在
media_path 输入时调用。使用 ultralytics model.track + bytetrack，
不依赖 supervision，与你实测通过的检测方式一致。

返回符合 SCENE-SCHEMA 的 dict 形式的 scene（含碰撞事件），供责任判定消费。
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import cv2


_CLS_TO_SCENE_TYPE = {
    "person": "pedestrian", "bicycle": "bicycle", "car": "car",
    "motorcycle": "motorcycle", "bus": "bus", "truck": "truck", "train": "other",
}


class VideoTracker:
    def __init__(self, model_name="yolov8s.pt", conf=0.3, iou=0.6, imgsz=640):
        self._conf, self._iou, self._imgsz = conf, iou, imgsz
        from ultralytics import YOLO
        self._model = YOLO(model_name)

    def _run_track(self, source, fps):
        tracks: dict[int, dict] = {}
        votes: dict[int, Counter] = {}
        frame_idx = 0
        for result in self._model.track(
            source=source, tracker="bytetrack.yaml", persist=True,
            show=False, save=False, conf=self._conf, iou=self._iou,
            imgsz=self._imgsz, verbose=False, stream=True,
        ):
            boxes = result.boxes
            if boxes.id is None:
                frame_idx += 1
                continue
            fw, fh = result.orig_shape[1], result.orig_shape[0]
            t = frame_idx / fps
            for cls_id, tid, xyxy in zip(boxes.cls.tolist(), boxes.id.tolist(),
                                         boxes.xyxy.tolist()):
                name = self._model.names[int(cls_id)]
                tid = int(tid)
                votes.setdefault(tid, Counter())[name] += 1
                x1, y1, x2, y2 = xyxy
                cx, cy = ((x1 + x2) / 2) / fw, ((y1 + y2) / 2) / fh
                w, h = (x2 - x1) / fw, (y2 - y1) / fh
                td = tracks.setdefault(tid, {"type": name, "trajectory": []})
                if not td["trajectory"] or t - td["trajectory"][-1]["t"] >= 1.0:
                    td["trajectory"].append({"t": round(t, 3), "x": round(cx, 4),
                                             "y": round(cy, 4), "w": round(w, 4),
                                             "h": round(h, 4)})
            frame_idx += 1
        track_types = {tid: v.most_common(1)[0][0] for tid, v in votes.items()}
        return tracks, track_types

    def detect_events(self, tracks):
        events, ids = [], sorted(tracks.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                p, q = tracks[ids[i]], tracks[ids[j]]
                if not p["trajectory"] or not q["trajectory"]:
                    continue
                md, bt, bq = 1e9, None, None
                for x in p["trajectory"]:
                    for y in q["trajectory"]:
                        if abs(x["t"] - y["t"]) > 0.5:
                            continue
                        d = ((x["x"] - y["x"]) ** 2 + (x["y"] - y["y"]) ** 2) ** 0.5
                        if d < md:
                            md, bt, bq = d, x, y
                if bt is not None and md < 0.08:
                    overlap = not (bt["x"] + bt["w"] / 2 < bq["x"] - bq["w"] / 2
                                   or bq["x"] + bq["w"] / 2 < bt["x"] - bt["w"] / 2
                                   or bt["y"] + bt["h"] / 2 < bq["y"] - bq["h"] / 2
                                   or bq["y"] + bq["h"] / 2 < bt["y"] - bt["h"] / 2)
                    events.append({"time": round((bt["t"] + bq["t"]) / 2, 2),
                                   "type": "collision" if overlap else "near_miss",
                                   "participants": [ids[i], ids[j]],
                                   "confidence": round(min(1.0, 1.0 - md * 10), 2)})
        return events

    def perceive(self, video_path: str) -> dict:
        """返回 scene 字典（dict 形式，符合 SCENE-SCHEMA）。"""
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        cap.release()
        tracks, track_types = self._run_track(video_path, fps)

        vehicles = []
        for tid, td in tracks.items():
            pts = td["trajectory"]
            ms = 0.0
            if len(pts) >= 2 and pts[-1]["t"] - pts[0]["t"] > 0:
                ms = abs(pts[-1]["x"] - pts[0]["x"]) / (pts[-1]["t"] - pts[0]["t"]) * 100.0
            vehicles.append({"id": tid,
                             "type": _CLS_TO_SCENE_TYPE.get(track_types[tid], "other"),
                             "trajectory": pts, "max_speed_kmh": round(ms, 1)})

        return {
            "$schema": "scene.v1.json",
            "scene_id": Path(video_path).stem,
            "source": "video",
            "vehicles": vehicles,
            "events": self.detect_events(tracks),
            "road": "unknown", "lane_markings": "unknown",
            "traffic_light": "unknown", "visibility": "unknown",
            "confidence": 0.5,
        }
