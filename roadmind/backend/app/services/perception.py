"""
视频/照片感知服务（M1）。

- use_mock / 无输入：从文字描述生成 mock 场景（保证无视频也能跑通）；
- 传入 scene 字典：直接构建 Scene（外部已用 YOLO 检出 scene.json）；
- 传入媒体文件路径：使用 VideoPerceiver 做真实视频检测（迭代阶段启用）。
"""
from __future__ import annotations

from pathlib import Path

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

    def scene_from_dict(self, data: dict, scene_id: str | None = None) -> Scene:
        """从外部生成的 scene 字典/JSON 构建 Scene 对象（跳过感知 mock）。"""
        data = dict(data) or {}
        data["scene_id"] = scene_id or data.get("scene_id", "case")
        return Scene(**data)

    def scene_from_json_file(self, path: str, scene_id: str | None = None) -> Scene:
        import json

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return self.scene_from_dict(data, scene_id)

    async def perceive(
        self,
        scene_id: str,
        text: str | None,
        scene_dict: dict | None = None,
        media_path: str | None = None,
    ) -> Scene:
        """入口。优先级：scene_dict(外部scene) > media(真实视频检测) > mock(文字)。"""
        if scene_dict:
            return self.scene_from_dict(scene_dict, scene_id)
        if media_path:
            # 迭代阶段：真实视频检测（VideoPerceiver），参数取自配置
            from app.services.detector import VideoPerceiver

            per = VideoPerceiver(
                model_name=settings.yolo_model,
                conf=settings.yolo_conf,
                iou=settings.yolo_iou,
                imgsz=settings.yolo_imgsz,
                frame_step=settings.yolo_frame_step,
                track_activation_threshold=settings.yolo_track_threshold,
                lost_track_buffer=settings.yolo_lost_buffer,
            )
            scene, _ = per.perceive(media_path, scene_id)
            return scene
        if settings.use_mock:
            return self.mock_scene_from_text(scene_id, text or "路口两车碰撞，疑似追尾")
        raise NotImplementedError("真实感知待配置")


perception_service = PerceptionService()
