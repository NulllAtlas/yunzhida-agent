"""
视频/照片感知服务（M1）。

- 配置了 `PERCEPTION_SERVICE_URL` 时，调用 P3 的 `POST /perceive` 拿真实 scene.json；
  任何失败（网络/超时/解析）都自动回落本地降级，绝不让任务失败（D6）。
- 未配置时走本地降级：由文字生成低置信 mock 场景，并在有视频时按 D8 策略抽帧，
  把关键帧路径挂到事件上，供 P3 检测与前端取证展示。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings
from app.schemas.models import Scene, SceneEvent, Vehicle, TrajectoryPoint
from app.services.frames import frame_extractor

logger = logging.getLogger(__name__)

_ACCIDENT_KEYWORDS = ["追尾", "变道", "路口", "让行", "碰撞", "撞", "行人", "转弯"]

# 认定一个响应确实像 scene 的字段集合：Scene 各字段都有默认值，
# 不加这道门会把任意 JSON（如 {"foo":"bar"}）都当成合法的空场景。
_SCENE_KEYS = {
    "source", "vehicles", "events", "road",
    "lane_markings", "traffic_light", "visibility", "confidence",
}


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
        """入口：优先调 P3 感知服务，失败/未配置则回落本地降级。"""
        if settings.perception_service_url:
            scene = await self._call_remote(scene_id, text, video_path)
            if scene is not None:
                return scene
            logger.warning("P3 感知服务不可用，回落本地降级场景 scene_id=%s", scene_id)
        return self._local_scene(scene_id, text, video_path)

    async def _call_remote(
        self, scene_id: str, text: str | None, video_path: str | None
    ) -> Scene | None:
        """调用 P3 `POST /perceive`，返回 None 表示失败需回落。"""
        url = settings.perception_service_url.rstrip("/") + "/perceive"
        payload = {"scene_id": scene_id, "text": text, "video_path": video_path}
        try:
            async with httpx.AsyncClient(timeout=settings.perception_timeout_s) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data: Any = resp.json()
        except Exception:  # noqa: BLE001 —— 网络/超时/非 2xx 均回落
            logger.exception("调用 P3 感知服务失败：%s", url)
            return None

        # 兼容 {"code":0,"data":{...}} 与直接返回 scene 对象两种写法
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = data["data"]
        if not isinstance(data, dict):
            logger.warning("P3 感知服务返回结构不可解析：%r", type(data))
            return None
        if not (_SCENE_KEYS & data.keys()):
            logger.warning("P3 感知服务返回缺少 scene 字段，回落本地：%r", sorted(data)[:6])
            return None
        if not data.get("scene_id"):
            data = {**data, "scene_id": scene_id}
        try:
            return Scene.model_validate(data)
        except Exception:  # noqa: BLE001 —— 字段不合法同样回落
            logger.exception("P3 感知服务返回字段不合法，回落本地")
            return None

    def _local_scene(
        self, scene_id: str, text: str | None, video_path: str | None
    ) -> Scene:
        """本地降级：文字 mock 场景 + D8 抽帧关键帧。"""
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
        return scene


perception_service = PerceptionService()