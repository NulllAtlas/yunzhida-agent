"""
视频/照片感知服务（M1）。

MVP 阶段：提供低精度占位实现 ——
- 从文字描述生成 mock 场景（保证无视频也能跑通）；
- 输入视频时返回低置信 mock 场景并提示可能需补录（真实检测在迭代阶段接入，如 YOLO）。
"""
from __future__ import annotations

from app.core.config import settings
from app.schemas.models import Scene, SceneEvent, Vehicle, TrajectoryPoint

_ACCIDENT_KEYWORDS = ["追尾", "变道", "路口", "让行", "碰撞", "撞", "行人", "转弯"]


class PerceptionService:
    def mock_scene_from_text(self, scene_id: str, text: str) -> Scene:
        """MVP 兜底：由文字描述生成一个低置信 mock 场景，保证全链路可跑。"""
        event_type = "collision"
        if "追尾" in text:
            event_type = "rear_end"
        elif "行人" in text or "撞人" in text:
            event_type = "vehicle_pedestrian"
        confidence = 0.6
        traffic_light = "unknown"
        if "灯" in text:
            traffic_light = "green" if "绿" in text else "red"
        scene = Scene(
            scene_id=scene_id,
            source="text",
            vehicles=[
                Vehicle(id=1, type="car", max_speed_kmh=50.0,
                        trajectory=[TrajectoryPoint(t=0.0, x=0.5, y=0.7, speed_kmh=50.0)]),
                Vehicle(id=2, type="car", max_speed_kmh=45.0,
                        trajectory=[TrajectoryPoint(t=12.0, x=0.6, y=0.6, speed_kmh=45.0)]),
            ],
            events=[SceneEvent(time=12.0, type=event_type, participants=[1, 2])],
            road="urban_intersection",
            traffic_light=traffic_light,
            visibility="day",
            confidence=confidence,
        )
        return scene

    async def perceive(self, scene_id: str, text: str | None) -> Scene:
        """入口：MVP 阶段始终返回 mock 场景。迭代阶段在此接入真实视频检测。"""
        if settings.use_mock:
            return self.mock_scene_from_text(scene_id, text or "路口两车碰撞，疑似追尾")
        # TODO(迭代): 真实视频感知（YOLO 抽帧检测 + 轨迹提取）
        raise NotImplementedError("真实视频感知待实现")


perception_service = PerceptionService()
