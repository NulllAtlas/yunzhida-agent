"""视频分帧服务（D8：大视频分帧处理策略）。

大视频（数分钟、数百 MB）不能逐帧解码 —— 内存与耗时都不可控。这里采用的策略：

1. 先读元信息（帧率 / 总帧数 / 时长），按"目标帧数"算出**均匀采样间隔**；
2. 用 `CAP_PROP_POS_MSEC` 直接定位采样点，跳过无用帧，不做全片解码；
3. 长边等比缩放到 `frame_max_width`，降低后续检测（P3）开销；
4. 三重上限保护：最多 `video_max_frames` 帧、最长 `video_max_duration_s` 秒
   （超长视频仅采样并标记 `truncated`）、抽帧总耗时 `video_extract_timeout_s` 熔断；
5. 任何失败都不抛异常，返回带 `error` 的结果，由上层回落到文字降级链路。

产出的关键帧路径会挂到 `Scene.events[*].keyframe`，供 P3 检测与前端取证展示。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings


@dataclass
class ExtractedFrame:
    index: int
    ts_ms: float
    path: str
    width: int
    height: int


@dataclass
class FrameResult:
    frames: list[ExtractedFrame] = field(default_factory=list)
    fps: float = 0.0
    total_frames: int = 0
    duration_s: float = 0.0
    sampled_interval_s: float = 0.0
    truncated: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.frames)


class FrameExtractor:
    def extract(
        self,
        video_path: str | Path,
        out_dir: str | Path,
        *,
        max_frames: int | None = None,
        max_width: int | None = None,
        max_duration_s: float | None = None,
        timeout_s: float | None = None,
        jpeg_quality: int | None = None,
    ) -> FrameResult:
        """按策略抽样抽帧，返回结果（失败时 error 非空，不抛异常）。"""
        max_frames = settings.video_max_frames if max_frames is None else max_frames
        max_width = settings.frame_max_width if max_width is None else max_width
        max_duration_s = settings.video_max_duration_s if max_duration_s is None else max_duration_s
        timeout_s = settings.video_extract_timeout_s if timeout_s is None else timeout_s
        quality = settings.frame_jpeg_quality if jpeg_quality is None else jpeg_quality

        src = Path(video_path)
        if not src.is_file():
            return FrameResult(error=f"视频文件不存在：{src}")

        try:
            import cv2  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            return FrameResult(error=f"opencv 不可用：{exc}")

        cap = cv2.VideoCapture(str(src))
        if not cap.isOpened():
            cap.release()
            return FrameResult(error=f"无法解码视频：{src.name}")

        try:
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            duration = total / fps if fps > 0 else 0.0
            truncated = duration > max_duration_s
            span = min(duration, max_duration_s) if duration > 0 else max_duration_s
            interval = span / max_frames if max_frames > 0 else 1.0
            if interval <= 0:
                interval = 1.0

            dest = Path(out_dir)
            dest.mkdir(parents=True, exist_ok=True)
            started = time.monotonic()
            frames: list[ExtractedFrame] = []

            for i in range(max(0, max_frames)):
                if time.monotonic() - started > timeout_s:
                    truncated = True
                    break
                cap.set(cv2.CAP_PROP_POS_MSEC, i * interval * 1000.0)
                ok, img = cap.read()
                if not ok or img is None:
                    continue
                h, w = img.shape[:2]
                if max_width and w > max_width:
                    scale = max_width / float(w)
                    img = cv2.resize(
                        img, (max_width, max(1, int(h * scale))), interpolation=cv2.INTER_AREA
                    )
                h, w = img.shape[:2]
                path = dest / f"frame_{i:03d}.jpg"
                cv2.imwrite(str(path), img, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
                frames.append(
                    ExtractedFrame(
                        index=i, ts_ms=round(i * interval * 1000.0, 3),
                        path=str(path), width=w, height=h,
                    )
                )
        finally:
            cap.release()

        return FrameResult(
            frames=frames,
            fps=round(fps, 3),
            total_frames=total,
            duration_s=round(duration, 3),
            sampled_interval_s=round(interval, 3),
            truncated=truncated,
        )


frame_extractor = FrameExtractor()