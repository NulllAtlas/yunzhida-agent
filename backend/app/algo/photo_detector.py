"""
现场照片单帧检测（M1·照片证据）。

和 video_tracker 的分工：
- 视频靠多帧轨迹给出速度与碰撞事件；
- 照片只有一帧，`detect_events` 需要 ≥2 个轨迹点，单帧喂进去事件必为空，
  所以照片走独立的 `model.predict` 路径，产出的是"现场有什么"——目标类别、
  位置、信号灯颜色。

照片是静态画面，给不出速度/方向，因此它的结论只作为**补充证据**进判定上下文，
不参与 judge 的事故门控（门控依赖速度与碰撞置信度，只有视频来源才够资格）。

类别映射与信号灯判色复用 video_tracker 里的实现，避免同一套规则写两遍。
"""
from __future__ import annotations

import logging
from pathlib import Path

import cv2

from app.algo.video_tracker import (
    _CLS_TO_SCENE_TYPE,
    _SCENE_ELEMENT_TYPES,
    _crop_box,
    aggregate_light_state,
    classify_light_color,
)

logger = logging.getLogger(__name__)

# 静态画面的局限说明：前端与判定 prompt 都会原样展示，不能省
_STATIC_LIMIT = "静态画面（单帧），无法判断运动速度与方向"


def to_target(cls_name: str, conf: float, xyxy: list[float],
              fw: int, fh: int) -> dict | None:
    """把一个检测框转成 PhotoTarget 字典；场景要素（信号灯/标志牌）返回 None。

    抽成纯函数是为了能脱离 YOLO 模型单测：照片进检测链的映射规则就在这里，
    "信号灯不能被当成事故目标"这种行为必须有测试锁住。
    """
    if cls_name in _SCENE_ELEMENT_TYPES:
        return None
    x1, y1, x2, y2 = xyxy
    return {
        "type": _CLS_TO_SCENE_TYPE.get(cls_name, "other"),
        "confidence": round(float(conf), 3),
        # 归一化 bbox：x/y 左上角，w/h 宽高
        "bbox": [round(x1 / fw, 4), round(y1 / fh, 4),
                 round((x2 - x1) / fw, 4), round((y2 - y1) / fh, 4)],
    }


class PhotoDetector:
    """YOLO 单帧检测器（惰性加载模型，mock 模式零开销）。"""

    def __init__(self, model_name: str = "yolov8s.pt", conf: float = 0.3,
                 imgsz: int = 640) -> None:
        self._model_name = model_name
        self._conf = conf
        self._imgsz = imgsz
        self._model = None

    def _get_model(self):
        """首次调用才 import ultralytics（与 VideoTracker 同样的惰性策略）。"""
        if self._model is None:
            from ultralytics import YOLO

            self._model = YOLO(self._model_name)
        return self._model

    def detect(self, photo_path: str) -> dict:
        """检测一张照片，返回 PhotoEvidence 兼容的 dict。

        任何失败（读不出图 / 模型不可用 / 推理异常）都返回**空的** targets 并带上
        note 说明原因 —— 与 perception._degraded_scene 同一原则：绝不编造检测结果。
        """
        evidence: dict = {
            "name": Path(photo_path).name,
            "width": 0,
            "height": 0,
            "targets": [],
            "traffic_light": "unknown",
            "note": "",
        }

        img = cv2.imread(str(photo_path))
        if img is None:
            evidence["note"] = "照片无法读取（可能不是有效图片），未做检测"
            return evidence

        fh, fw = img.shape[:2]
        evidence["width"], evidence["height"] = fw, fh

        try:
            results = self._get_model().predict(
                source=img, conf=self._conf, imgsz=self._imgsz, verbose=False
            )
        except Exception:  # noqa: BLE001 — 无 ultralytics / 权重缺失 / 推理异常
            logger.exception("photo detect failed: %s", photo_path)
            evidence["note"] = "照片检测失败（模型不可用或图片异常），未产出检出目标"
            return evidence

        lights: list[str] = []
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None or len(boxes) == 0:
                continue
            names = getattr(self._model, "names", {}) or {}
            for cls_id, conf, xyxy in zip(
                boxes.cls.tolist(), boxes.conf.tolist(), boxes.xyxy.tolist()
            ):
                cls_name = str(names.get(int(cls_id), "")).lower()

                # 信号灯/标志牌是场景要素不是交通参与者，单独按颜色汇报，
                # 不混进 targets（与视频侧 _SCENE_ELEMENT_TYPES 的处理保持一致）
                if cls_name in _SCENE_ELEMENT_TYPES:
                    if cls_name == "traffic light":
                        x1, y1, x2, y2 = xyxy
                        nx, ny = x1 / fw, y1 / fh
                        nw, nh = (x2 - x1) / fw, (y2 - y1) / fh
                        crop = _crop_box(
                            img,
                            {"x": nx + nw / 2, "y": ny + nh / 2, "w": nw, "h": nh},
                            fw,
                            fh,
                        )
                        state = classify_light_color(crop)
                        if state:
                            lights.append(state)
                    continue

                target = to_target(cls_name, conf, xyxy, fw, fh)
                if target:
                    evidence["targets"].append(target)

        evidence["traffic_light"] = aggregate_light_state(
            [{"state": s} for s in lights]
        )
        evidence["note"] = self._note(evidence)
        return evidence

    @staticmethod
    def _note(evidence: dict) -> str:
        """如实说明这张照片给出了什么、给不出什么。"""
        if not evidence["targets"] and evidence["traffic_light"] == "unknown":
            return f"照片中未检出可辨认的目标或信号灯；{_STATIC_LIMIT}"
        return f"{_STATIC_LIMIT}（照片仅能佐证现场目标与信号灯状态）"


photo_detector = PhotoDetector()
