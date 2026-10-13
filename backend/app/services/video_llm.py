"""
视频 LLM 智能分段服务（长视频优化）。

通过调用多模态视频 LLM（如 Qwen-VL-Video）分析长视频内容，
识别关键事件片段并返回分段建议，只对高优先级片段进行精细处理。
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class VideoSegment:
    """视频片段"""
    start: float
    end: float
    description: str
    priority: float  # 0.0-1.0，越高越重要


@dataclass
class SegmentResult:
    """分段处理结果"""
    segment: VideoSegment
    scene: Optional[dict]  # 该段的检测结果
    error: Optional[str] = None


class VideoSegmenter:
    """视频 LLM 分段器"""
    
    def __init__(self):
        self.client: Optional[AsyncOpenAI] = None
        self._init_client()
    
    def _init_client(self):
        """初始化 LLM 客户端"""
        if settings.moma_base_url and settings.moma_api_key:
            self.client = AsyncOpenAI(
                api_key=settings.moma_api_key,
                base_url=settings.moma_base_url,
                timeout=settings.video_llm_timeout_s,
            )
            logger.info(
                "Video LLM client initialized: model=%s, url=%s",
                settings.video_llm_model,
                settings.moma_base_url,
            )
        else:
            logger.warning(
                "Video LLM client not configured: missing MOMA_BASE_URL or MOMA_API_KEY"
            )
    
    async def segment_video(self, video_path: str) -> list[VideoSegment]:
        """
        调用视频 LLM 分析并返回分段建议。
        
        策略：
        1. 提取关键帧（每 30 秒一帧）
        2. 调用多模态 LLM 分析关键帧
        3. 解析返回的分段建议
        
        返回按优先级降序排列的片段列表。
        """
        if not self.client:
            logger.warning("Video LLM client not available, skipping segmentation")
            return []
        
        try:
            # 1. 提取关键帧
            keyframes = await asyncio.to_thread(
                self._extract_keyframes, video_path, interval=30
            )
            
            if not keyframes:
                logger.warning("No keyframes extracted from %s", video_path)
                return []
            
            # 2. 调用 LLM 分析
            segments = await self._analyze_keyframes(keyframes)
            
            # 3. 按优先级降序排序
            segments.sort(key=lambda s: s.priority, reverse=True)
            
            logger.info(
                "Video segmentation complete: %d segments from %s",
                len(segments),
                video_path,
            )
            
            return segments
            
        except Exception as exc:
            logger.exception("Video segmentation failed: %s", video_path)
            return []
    
    def _extract_keyframes(self, video_path: str, interval: int = 30) -> list[dict]:
        """
        提取关键帧。
        
        Args:
            video_path: 视频文件路径
            interval: 提取间隔（秒）
        
        Returns:
            关键帧列表：[{"time": float, "path": str, "image": bytes}, ...]
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error("Cannot open video: %s", video_path)
            return []
        
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
            
            keyframes = []
            frame_no = 0
            
            while True:
                # 跳转到指定帧
                target_frame = int(frame_no * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                
                ok, frame = cap.read()
                if not ok:
                    break
                
                # 缩放到合理尺寸（避免 token 过多）
                frame = cv2.resize(frame, (width, height))
                
                # 编码为 JPEG
                _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                
                keyframes.append({
                    "time": frame_no,
                    "path": f"frame_{frame_no}s.jpg",
                    "image": buffer.tobytes(),
                })
                
                frame_no += interval
                
                if frame_no > duration:
                    break
            
            logger.info(
                "Extracted %d keyframes from %s (duration=%.1fs)",
                len(keyframes),
                video_path,
                duration,
            )
            
            return keyframes
            
        finally:
            cap.release()
    
    async def _analyze_keyframes(self, keyframes: list[dict]) -> list[VideoSegment]:
        """
        调用 LLM 分析关键帧，返回分段建议。
        
        Prompt 设计：
        - 要求返回严格的 JSON 格式
        - 只返回 priority > 0.5 的事故相关片段
        - 描述要简洁（用于后续处理参考）
        """
        # 构建消息：关键帧 + 分析指令
        content = [
            {
                "type": "text",
                "text": """
你是一名交通事故分析专家。请分析这些行车记录仪关键帧，识别可能的事故相关片段。

请按以下 JSON 格式返回分析结果：
{
    "segments": [
        {
            "start": 0.0,
            "end": 120.5,
            "description": "正常行驶，道路畅通",
            "priority": 0.3
        },
        {
            "start": 120.5,
            "end": 145.0,
            "description": "疑似碰撞事件，两车接触",
            "priority": 0.9
        }
    ]
}

要求：
1. 只返回 priority > 0.5 的片段（事故相关或异常情况）
2. start/end 为时间戳（秒），基于关键帧的时间推断
3. description 简洁描述该片段内容（20 字以内）
4. priority 评分标准：
   - 0.9-1.0: 明确碰撞/事故
   - 0.7-0.9: 疑似事故/紧急避让
   - 0.5-0.7: 异常情况（急刹、行人横穿等）
   - <0.5: 正常行驶（不返回）

当前分析的视频共 %d 个关键帧，时间跨度约 %d 秒。
"""
                % (len(keyframes), keyframes[-1]["time"] if keyframes else 0),
            }
        ]
        
        # 添加关键帧图片
        for kf in keyframes[:10]:  # 限制最多 10 帧（避免 token 超限）
            import base64
            image_base64 = base64.b64encode(kf["image"]).decode("utf-8")
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{image_base64}"
                },
            })
        
        try:
            response = await self.client.chat.completions.create(
                model=settings.video_llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是专业的交通事故分析助手，擅长从视频关键帧识别事故事件。",
                    },
                    {"role": "user", "content": content},
                ],
                temperature=0.3,  # 降低随机性，保证输出格式稳定
                max_tokens=1000,
            )
            
            # 解析返回结果
            result_text = response.choices[0].message.content.strip()
            logger.debug("LLM response: %s", result_text)
            
            # 提取 JSON（可能包含在代码块中）
            json_str = self._extract_json(result_text)
            if not json_str:
                logger.error("Failed to extract JSON from LLM response")
                return []
            
            data = json.loads(json_str)
            segments = []
            
            for seg_data in data.get("segments", []):
                try:
                    segment = VideoSegment(
                        start=float(seg_data.get("start", 0)),
                        end=float(seg_data.get("end", 0)),
                        description=str(seg_data.get("description", "")),
                        priority=float(seg_data.get("priority", 0)),
                    )
                    if segment.priority > 0.5:
                        segments.append(segment)
                except (ValueError, TypeError) as e:
                    logger.warning("Invalid segment data: %s, error: %s", seg_data, e)
            
            return segments
            
        except Exception as exc:
            logger.exception("LLM analysis failed: %s", exc)
            return []
    
    def _extract_json(self, text: str) -> Optional[str]:
        """从 LLM 响应中提取 JSON 字符串"""
        # 尝试直接解析
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            pass
        
        # 尝试提取代码块中的 JSON
        import re
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            return match.group(1)
        
        # 尝试提取第一个 { 到最后一个 }
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return text[start:end]
        
        return None


class VideoSegmentProcessor:
    """视频片段处理器"""
    
    def __init__(self, tracker):
        """
        Args:
            tracker: VideoTracker 实例（用于实际检测）
        """
        self.tracker = tracker
        self.segmenter = VideoSegmenter()
    
    async def process_long_video(
        self,
        video_path: str,
        scene_id: str,
        annotate_dir: str | None = None,
    ) -> dict:
        """
        处理长视频：智能分段 + 并行检测。
        
        流程：
        1. LLM 分析并返回高优先级片段
        2. 截取各片段
        3. 并行运行 YOLO 检测
        4. 整合结果
        
        Args:
            video_path: 原视频路径
            scene_id: 场景 ID
            annotate_dir: 标注输出目录
        
        Returns:
            整合后的 scene dict
        """
        from app.services.video_clip import extract_clip
        from pathlib import Path
        
        # 1. LLM 分段
        segments = await self.segmenter.segment_video(video_path)
        
        if not segments:
            logger.warning("No segments from LLM, falling back to full video processing")
            # 降级：处理整个视频
            return self.tracker.perceive(video_path, annotate_dir)
        
        # 2. 截取并处理各片段
        results: list[SegmentResult] = []
        tasks = []
        
        video_path_obj = Path(video_path)
        temp_dir = video_path_obj.parent / "temp_segments"
        temp_dir.mkdir(exist_ok=True)
        
        for i, segment in enumerate(segments[:5]):  # 限制最多处理 5 个片段
            # 截取片段
            segment_path = temp_dir / f"{scene_id}_seg{i}.mp4"
            
            clip_meta = extract_clip(
                str(video_path),
                str(segment_path),
                start_s=segment.start,
                end_s=segment.end,
            )
            
            if not clip_meta["ok"]:
                logger.warning(
                    "Failed to extract segment %d (%.1f-%.1fs): %s",
                    i,
                    segment.start,
                    segment.end,
                    clip_meta.get("error"),
                )
                results.append(SegmentResult(
                    segment=segment,
                    scene=None,
                    error=clip_meta.get("error"),
                ))
                continue
            
            # 异步检测
            task = asyncio.create_task(
                asyncio.to_thread(
                    self.tracker.perceive,
                    str(segment_path),
                    annotate_dir,
                )
            )
            tasks.append((task, segment, segment_path))
        
        # 3. 等待所有检测完成
        for task, segment, segment_path in tasks:
            try:
                scene = await task
                results.append(SegmentResult(
                    segment=segment,
                    scene=scene,
                    error=None,
                ))
                logger.info(
                    "Segment processed: %.1f-%.1fs, %d vehicles, %d events",
                    segment.start,
                    segment.end,
                    len(scene.get("vehicles", [])),
                    len(scene.get("events", [])),
                )
            except Exception as exc:
                logger.exception("Segment processing failed: %s", exc)
                results.append(SegmentResult(
                    segment=segment,
                    scene=None,
                    error=str(exc),
                ))
        
        # 4. 整合结果
        merged_scene = self._merge_results(results, scene_id, video_path)
        
        # 5. 清理临时文件
        try:
            for _, _, segment_path in tasks:
                if segment_path.exists():
                    segment_path.unlink()
            if temp_dir.exists() and not any(temp_dir.iterdir()):
                temp_dir.rmdir()
        except Exception as exc:
            logger.warning("Failed to clean up temp files: %s", exc)
        
        return merged_scene
    
    def _merge_results(
        self,
        results: list[SegmentResult],
        scene_id: str,
        video_path: str,
    ) -> dict:
        """
        合并各片段检测结果。
        
        策略：
        1. 合并所有车辆（重编号 ID）
        2. 合并所有事件（时间戳偏移修正）
        3. 取最高置信度作为整体置信度
        4. 标注"分段处理"标记
        """
        from pathlib import Path
        
        merged_vehicles = []
        merged_events = []
        merged_lights = []
        
        vehicle_id_offset = 0
        max_confidence = 0.0
        
        for result in results:
            if result.scene is None:
                logger.warning(
                    "Skipping segment %.1f-%.1fs: %s",
                    result.segment.start,
                    result.segment.end,
                    result.error,
                )
                continue
            
            scene = result.scene
            time_offset = result.segment.start
            
            # 合并车辆（重编号）
            for vehicle in scene.get("vehicles", []):
                new_vehicle = vehicle.copy()
                new_vehicle["id"] = vehicle["id"] + vehicle_id_offset
                # 修正轨迹时间戳
                for point in new_vehicle.get("trajectory", []):
                    point["t"] += time_offset
                merged_vehicles.append(new_vehicle)
            
            vehicle_id_offset += len(scene.get("vehicles", [])) or 1
            
            # 合并事件（修正时间戳）
            for event in scene.get("events", []):
                new_event = event.copy()
                new_event["time"] += time_offset
                new_event["segment"] = {
                    "start": result.segment.start,
                    "end": result.segment.end,
                    "description": result.segment.description,
                }
                merged_events.append(new_event)
            
            # 合并信号灯
            for light in scene.get("traffic_lights", []):
                merged_lights.append(light)
            
            # 更新最高置信度
            max_confidence = max(max_confidence, scene.get("confidence", 0.0))
        
        # 构建合并后的 scene
        merged_scene = {
            "$schema": "scene.v1.json",
            "scene_id": scene_id,
            "source": "video",
            "vehicles": merged_vehicles,
            "events": merged_events,
            "traffic_lights": merged_lights,
            "road": "unknown",
            "lane_markings": "unknown",
            "traffic_light": "unknown",  # TODO: 跨片段汇总
            "visibility": "unknown",
            "confidence": max_confidence,
            # 标注分段处理元信息
            "_segmented": True,
            "_segment_count": len(results),
            "_original_duration": self._get_video_duration(video_path),
        }
        
        logger.info(
            "Merged scene: %d vehicles, %d events from %d segments",
            len(merged_vehicles),
            len(merged_events),
            len(results),
        )
        
        return merged_scene
    
    def _get_video_duration(self, video_path: str) -> float:
        """获取视频时长（秒）"""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return 0.0
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        cap.release()
        return frames / fps if fps > 0 else 0.0


# 全局实例
video_segmenter = VideoSegmenter()
