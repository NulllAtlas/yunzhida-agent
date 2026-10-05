"""
视频/照片感知服务（M1）。

MVP 阶段：提供低精度占位实现 ——
- 从文字描述生成 mock 场景（保证无视频也能跑通）；
- 输入视频时返回低置信 mock 场景并提示可能需补录（真实检测在迭代阶段接入，如 YOLO）。
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.schemas.models import Scene, SceneEvent, Vehicle, TrajectoryPoint
from app.services.frames import frame_extractor

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

    async def perceive(
        self, scene_id: str, text: str | None, video_path: str | None = None
    ) -> Scene:
        """入口：视频 → 场景（真实检测待 P3 提供 `POST /perceive`）。

        真实检测接入前统一走"文字降级"路径生成低置信场景；若提供了视频，
        先按 D8 策略抽样抽帧（大视频不逐帧解码），把关键帧路径挂到事件上，
        供 P3 做 YOLO 检测与前端取证展示。
        """
        scene = self.mock_scene_from_text(scene_id, text or "路口两车碰撞，疑似追尾")
        scene.confidence = settings.perception_confidence

        if video_path:
            result = frame_extractor.extract(video_path, Path(settings.frames_dir) / scene_id)
            if result.ok:
                scene.source = "video"
                keyframe = result.frames[len(result.frames) // 2].path
                if scene.events:
                    scene.events[0].keyframe = keyframe
                else:
                    scene.events = [
                        SceneEvent(time=0.0, type="collision", keyframe=keyframe)
                    ]
                # TODO(迭代/B): 把 result.frames 交给 P3 的 `POST /perceive`
                #              做检测 + 轨迹提取；失败时保持当前文字降级场景。
        return scene


perception_service = PerceptionService()
