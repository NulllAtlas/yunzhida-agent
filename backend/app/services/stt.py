"""语音输入（STT）：把用户的麦克风录音转写成中文文字。

优先走 MoMA 网关的 SenseVoice（/v1/audio/transcriptions，实测 300~600ms，
比本地 CPU 转写快一个量级，语音对话才能勉强来回）；网关未配置或调用失败
回退本地 faster-whisper（首次运行要下载 base 模型，加载也慢）。
转写失败由调用方静默降级（返回空串，不填输入框）。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

# faster-whisper 从 HuggingFace 拉模型，国内网络直连超时（实测 ConnectTimeout），
# 默认走 hf-mirror 镜像；调用方可用环境变量覆盖
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from openai import OpenAI

from app.core.config import settings  # noqa: E402

logger = logging.getLogger(__name__)

# base 模型 ~74MB，中文演示够用且下载快；CPU 单机转写 60s 音频约 10~20s
_MODEL_SIZE = "base"

# 模型惰性加载的单例：首次转写时下载/加载，之后复用（加载要几秒，不能每句都来）
_model = None
_gw_client: OpenAI | None = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        _model = WhisperModel(
            _MODEL_SIZE, device="cpu", compute_type="int8",
            download_root=str(Path(settings.db_path).parent / "whisper"),
        )
    return _model


def _get_gw_client() -> OpenAI:
    """网关转写客户端（同步，Gradio worker 线程里没有事件循环）。

    必须用 openai SDK：网关按 UA 分发，requests 直接打 chat/audio 路由会被
    nginx 拦成 404（实测），SDK 的 UA 能通过。
    """
    global _gw_client
    if _gw_client is None:
        _gw_client = OpenAI(
            base_url=settings.moma_base_url or None,
            api_key=settings.moma_api_key or "not-set",
            timeout=30,
            max_retries=0,
        )
    return _gw_client


def _gateway_ok() -> bool:
    return bool(settings.moma_base_url) and not settings.use_mock


def _transcribe_gateway(audio_path: str) -> str | None:
    """网关 SenseVoice 转写：失败返回 None（调用方回退本地 whisper）。

    网关抖动不能阻塞对话 —— 任何异常都只记日志后回退，转写永不 500。
    """
    if not _gateway_ok():
        return None
    try:
        with open(audio_path, "rb") as f:
            resp = _get_gw_client().audio.transcriptions.create(
                model=settings.stt_gateway_model or "SenseVoice",
                file=(Path(audio_path).name, f, "audio/wav"),
            )
        return (getattr(resp, "text", "") or "").strip()
    except Exception:  # noqa: BLE001 — 网关抖动回退本地，不阻塞对话
        logger.warning("stt gateway transcribe failed, falling back to local whisper",
                       exc_info=True)
        return None


def transcribe(audio_path: str | None) -> str:
    """把录音文件转写成中文文字；空路径/不可读/识别为空都返回空串。"""
    if not audio_path or not Path(audio_path).exists():
        return ""
    text = _transcribe_gateway(audio_path)
    if text is not None:
        return text
    try:
        segments, _info = _get_model().transcribe(
            audio_path, language="zh", vad_filter=True,
        )
        text = "".join(seg.text for seg in segments).strip()
        return text
    except Exception:  # noqa: BLE001 — 语音输入是增强能力，失败不阻塞对话
        logger.exception("stt transcribe failed: %s", audio_path)
        return ""
