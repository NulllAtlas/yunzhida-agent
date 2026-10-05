"""视频分帧策略（D8）回归测试。

合成一段小视频后验证抽样抽帧的数量上限、尺寸缩放、缺失文件容错，
以及感知节点是否把关键帧路径挂到 `Scene.events[*].keyframe`。
"""
from __future__ import annotations

import asyncio

import pytest

from app.core.config import settings
from app.services.frames import FrameExtractor
from app.services.perception import perception_service


def _load_cv2():
    """opencv / numpy 不可用（未安装或版本不兼容）时跳过，而不是让整套测试失败。"""
    try:
        import cv2
        import numpy as np
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"opencv/numpy 不可用：{exc}")
    return cv2, np


def _make_video(path, *, seconds: float = 3.0, fps: int = 10, size=(320, 240)) -> str:
    """用 MJPG/AVI 合成测试视频（无需外部素材）。"""
    cv2, np = _load_cv2()
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, size)
    if not writer.isOpened():
        pytest.skip("当前环境无可用视频编码器（MJPG）")
    try:
        for i in range(int(seconds * fps)):
            frame = np.full((size[1], size[0], 3), (i * 7) % 255, dtype="uint8")
            writer.write(frame)
    finally:
        writer.release()
    return str(path)


def test_extract_samples_bounded_frames(tmp_path):
    """3 秒视频按 max_frames=5 抽样：帧数不超过上限，且长边缩放到 max_width。"""
    video = _make_video(tmp_path / "clip.avi", seconds=3.0, fps=10)
    result = FrameExtractor().extract(
        video, tmp_path / "out", max_frames=5, max_width=200, timeout_s=30
    )

    assert result.ok, result.error
    assert 0 < len(result.frames) <= 5
    assert result.duration_s > 0
    assert result.sampled_interval_s > 0
    for frame in result.frames:
        assert frame.path.endswith(".jpg")
        assert frame.width <= 200
        assert frame.height > 0
        import os

        assert os.path.getsize(frame.path) > 0


def test_extract_respects_max_frames_of_two(tmp_path):
    """上限收紧到 2 时不能多抽。"""
    video = _make_video(tmp_path / "clip2.avi", seconds=2.0, fps=10)
    result = FrameExtractor().extract(video, tmp_path / "out2", max_frames=2, max_width=160)

    assert result.ok, result.error
    assert len(result.frames) <= 2


def test_extract_missing_file_returns_error_without_raising(tmp_path):
    """文件不存在时必须返回 error，而不是抛异常（上层据此走文字降级）。"""
    result = FrameExtractor().extract(tmp_path / "nope.mp4", tmp_path / "out3")

    assert result.ok is False
    assert result.error
    assert result.frames == []


def test_perceive_attaches_keyframe(tmp_path, monkeypatch):
    """有视频输入时：scene.source 变 video，关键帧路径写入 events[0].keyframe。"""
    video = _make_video(tmp_path / "clip3.avi", seconds=2.0, fps=10)
    monkeypatch.setattr(settings, "frames_dir", str(tmp_path / "frames"))

    scene = asyncio.run(perception_service.perceive("case-video", "追尾事故", video))

    assert scene.source == "video"
    assert scene.events and scene.events[0].keyframe
    import os

    assert os.path.exists(scene.events[0].keyframe)


def test_perceive_without_video_keeps_text_fallback():
    """无视频时保持文字降级路径不变。"""
    scene = asyncio.run(perception_service.perceive("case-text", "路口左转弯未让行"))

    assert scene.source == "text"
    assert scene.confidence == settings.perception_confidence