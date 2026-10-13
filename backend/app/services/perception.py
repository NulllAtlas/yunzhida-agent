"""
视频/照片感知服务（M1）。

- 视频 media_path 输入且 use_mock=False 时：走真实检测（内嵌 Algorithm 算法，
  app/algo/video_tracker.py，ultralytics YOLO 检测+追踪 → scene）；
- 现场照片输入时：走单帧检测（app/algo/photo_detector.py）→ scene.photos，
  照片给不出运动学，只作为补充证据，不参与事故门控；
- 传了视频但检测失败（无文件/无 ultralytics/检测异常）时：降级为**空的**
  source="text_fallback" 场景，如实标注检测失败，不编造检测结果；
- 无视频或 mock 模式：由文字描述生成 mock 场景，保证全链路可跑通。
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.algo.photo_detector import photo_detector
from app.algo.video_tracker import VideoTracker
from app.core.config import settings
from app.schemas.models import PhotoEvidence, Scene, SceneEvent, Vehicle, TrajectoryPoint
from app.services.scene_elements import enrich_scene_with_vision
from app.services.text_facts import extract_text_facts
from app.services.video_llm import VideoSegmentProcessor

logger = logging.getLogger(__name__)

_ACCIDENT_KEYWORDS = ["追尾", "变道", "路口", "让行", "碰撞", "撞", "行人", "转弯"]

# 照片证据的置信度折扣：静态单帧只能佐证"现场有什么"，弱于视频的运动学证据
_PHOTO_CONFIDENCE_FACTOR = 0.6


class PerceptionService:
    def __init__(self) -> None:
        self._tracker: VideoTracker | None = None

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

    def _get_tracker(self) -> VideoTracker:
        """惰性加载 YOLO 检测器（首次调用才 import ultralytics，mock 模式零开销）。"""
        if self._tracker is None:
            self._tracker = VideoTracker(
                model_name=settings.algo_model_name,
                conf=settings.algo_conf,
                vid_stride=settings.algo_vid_stride,
            )
        return self._tracker
    
    def _get_segment_processor(self) -> VideoSegmentProcessor:
        """惰性加载视频分段处理器（长视频优化）。"""
        return VideoSegmentProcessor(self._get_tracker())

    async def _track_video(self, scene_id: str, media_path: str) -> Scene:
        """真实感知：视频 → YOLO 检测+追踪 → scene dict → Scene。

        检测为 CPU/GPU 密集同步操作，放线程池执行避免阻塞事件循环。
        产出目录传给检测器：碰撞事件会生成标注了事故车辆识别框的关键帧。
        
        长视频优化：超过阈值时启用 LLM 智能分段处理。
        """
        from app.services.video_clip import probe_video
        
        # 检查是否需要分段处理
        duration, _, _, _ = probe_video(media_path)
        
        if duration > settings.long_video_threshold and not settings.use_mock:
            # 长视频：启用 LLM 智能分段
            logger.info(
                "Long video detected (%.1fs > %ds), using LLM segmentation",
                duration,
                settings.long_video_threshold,
            )
            try:
                processor = self._get_segment_processor()
                raw = await processor.process_long_video(
                    media_path,
                    scene_id,
                    settings.output_dir,
                )
                # 场景要素识别放在 try 内、Scene 构造之前：认不出会原样返回，
                # 而分段结果结构不对时仍然退回整段检测（与改造前的行为一致）
                raw = await enrich_scene_with_vision(raw, media_path)
                raw["scene_id"] = scene_id
                scene = Scene(**raw)
            except Exception as exc:
                logger.exception(
                    "LLM segmentation failed, falling back to full video: %s",
                    exc,
                )
                # 降级：处理整个视频
                raw = await asyncio.to_thread(
                    self._get_tracker().perceive, media_path, settings.output_dir
                )
                raw = await enrich_scene_with_vision(raw, media_path)
                raw["scene_id"] = scene_id
                scene = Scene(**raw)
        else:
            # 短视频或 mock 模式：直接处理整个视频
            raw = await asyncio.to_thread(
                self._get_tracker().perceive, media_path, settings.output_dir
            )
            # 路口场景要素识别（大模型看关键帧）：认出信号灯归属方向/人行横道/标线/
            # 标志牌就补进 scene；认不出（模型看不见图、账号未开通、超时）原样返回，
            # 链路退回 YOLO + HSV 的原有模式 —— 增强不生效也绝不能拖垮研判
            raw = await enrich_scene_with_vision(raw, media_path)
            raw["scene_id"] = scene_id
            scene = Scene(**raw)
        
        # keyframe 存的是落盘文件名；转成 /outputs/ 下的可访问 URL
        # （main.py 把 outputs 目录静态挂载在 /outputs），前端直接展示
        for ev in scene.events:
            if ev.keyframe:
                ev.keyframe = f"/outputs/{ev.keyframe}"
        return scene

    def _degraded_scene(self, scene_id: str) -> Scene:
        """视频检测失败时的降级场景。

        不编造任何 vehicle/event —— 之前降级路径复用 mock_scene_from_text 会凭空造出
        "两车 12 秒碰撞"并命中"追尾"关键词，把检测失败的推断包装成确定结论，
        用户无从分辨。这里如实留空，由 judge 节点压低置信度并在 reasoning 中说明。
        """
        return Scene(
            scene_id=scene_id,
            source="text_fallback",
            vehicles=[],
            events=[],
            road="unknown",
            lane_markings="unknown",
            traffic_light="unknown",
            visibility="unknown",
            confidence=0.3,
        )

    async def _detect_photos(self, photo_paths: list[str]) -> list[PhotoEvidence]:
        """逐张做单帧检测。

        mock 模式下不跑模型（测试要离线且快），但也**不编造**检出目标 ——
        只留文件名并用 note 说明没做检测。
        """
        if not photo_paths:
            return []
        if settings.use_mock:
            return [
                PhotoEvidence(name=Path(p).name, note="mock 模式未做真实照片检测")
                for p in photo_paths
            ]
        out: list[PhotoEvidence] = []
        for path in photo_paths:
            try:
                raw = await asyncio.to_thread(photo_detector.detect, path)
            except Exception:  # noqa: BLE001 — 检测器内部已兜底，这里再兜一层
                logger.exception("photo detect crashed: %s", path)
                raw = {"name": Path(path).name, "targets": [], "traffic_light": "unknown",
                       "note": "照片检测异常，未产出检出目标"}
            out.append(PhotoEvidence(**raw))
        return out

    def _photo_scene(self, scene_id: str, photos: list[PhotoEvidence]) -> Scene:
        """只有现场照片时的场景：静态证据，没有轨迹也没有事件。

        检出目标只放进 photos，**不塞进 vehicles** —— vehicles 承载的是视频里的
        运动学证据（门控与"共检出目标 N 个"都看它），把静态框混进去会同时污染
        两者的语义。
        """
        states = {
            p.traffic_light for p in photos if p.traffic_light not in ("unknown",)
        }
        if len(states) > 1:
            traffic_light = "mixed"
        elif states:
            traffic_light = states.pop()
        else:
            traffic_light = "unknown"

        return Scene(
            scene_id=scene_id,
            source="photo",
            vehicles=[],
            events=[],
            road="unknown",
            lane_markings="unknown",
            traffic_light=traffic_light,
            photos=photos,
            visibility="unknown",
            confidence=round(settings.perception_confidence * _PHOTO_CONFIDENCE_FACTOR, 3),
        )

    async def perceive(
        self,
        scene_id: str,
        text: str | None,
        media_path: str | None = None,
        photo_paths: list[str] | None = None,
    ) -> Scene:
        """入口：视频 / 照片 / 文字 → 场景。

        - 视频输入且 use_mock=False：走 YOLO 检测+追踪（Algorithm 算法）；
        - 无视频但有照片：单帧检测 → source="photo"（照片证据放在 scene.photos）；
        - 视频 + 照片：视频场景上附加照片证据（照片可补视频看不清的现场要素）；
        - 传了视频但检测失败/文件不存在：降级为 source="text_fallback" 的空场景，
          绝不编造检测结果；
        - 其余情况（无媒体输入 / mock 模式）：由文字生成文字场景，source="text"。
        """
        photos = await self._detect_photos(list(photo_paths or []))

        if media_path and not settings.use_mock:
            path = Path(media_path)
            if path.is_file():
                try:
                    scene = await self._track_video(scene_id, str(path))
                except Exception:  # noqa: BLE001 — 无 ultralytics/模型缺失/解析异常均降级
                    logger.exception("video perception failed, fallback to text: %s", media_path)
                    scene = self._degraded_scene(scene_id)
            else:
                logger.warning("media file not found, fallback to text: %s", media_path)
                scene = self._degraded_scene(scene_id)
        elif photos:
            # 纯照片提交：mock 模式下也走这里（宁可如实报"未做检测"，
            # 也不要复用 mock_scene_from_text 凭空造出"两车 12 秒追尾"当证据）
            scene = self._photo_scene(scene_id, photos)
        else:
            scene = self.mock_scene_from_text(scene_id, text or "路口两车碰撞，疑似追尾")
            scene.confidence = settings.perception_confidence

        # 视频场景（含降级场景）也把照片证据挂上，由 scene_summary 渲染进判定上下文
        if photos:
            scene.photos = photos
        # 用户补充文字里的现场要素（信号灯归属 / 路口指示牌 / 过错关键词）：
        # 以「用户陈述」身份随场景进判定上下文，不冒充检测结果。
        # 只留真的抽到东西的，免得给 prompt 塞一行空话。
        facts = extract_text_facts(text)
        if facts.matched:
            scene.text_facts = facts
        return scene


perception_service = PerceptionService()
