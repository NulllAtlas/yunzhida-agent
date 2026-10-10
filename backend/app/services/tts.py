"""文本转语音（TTS）：把助手的回复朗读成语音，语音对话能力的服务端。

edge-tts（微软 Edge 在线 TTS）：中文自然、无本地模型依赖，需联网；
合成失败由调用方静默降级（无音频，对话不受影响）。
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

# 中文女声（晓晓），自然度好且免费
_VOICE = "zh-CN-XiaoxiaoNeural"

# 朗读上限：过长文本合成慢且播放冗长，截断到这个字符数
_MAX_SPEAK_CHARS = 600


def _strip_markdown(text: str) -> str:
    """朗读用的纯文本：去掉 markdown 符号与 URL，避免念出星号井号。"""
    text = re.sub(r"https?://\S+", "链接", text)
    text = re.sub(r"!?\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"[#*_>`~|]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _out_path() -> Path:
    out_dir = Path(settings.output_dir) / "tts"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"tts_{uuid.uuid4().hex[:12]}.mp3"


async def _run(clean: str, path: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(clean, voice=_VOICE)
    await communicate.save(str(path))


def synthesize(text: str) -> str | None:
    """同步版：Gradio 的 worker 线程调用（线程里没有事件循环，
    asyncio.run 起临时循环执行）；失败返回 None。
    """
    clean = _strip_markdown(text or "")[:_MAX_SPEAK_CHARS]
    if not clean:
        return None
    path = _out_path()
    try:
        asyncio.run(_run(clean, path))
    except Exception:  # noqa: BLE001 — 语音是增强能力，失败不阻塞对话
        logger.exception("tts synthesize failed")
        return None
    if path.exists() and path.stat().st_size > 0:
        return str(path)
    return None


async def synthesize_async(text: str) -> str | None:
    """异步版：FastAPI 的 async 端点直接 await（事件循环内不能 asyncio.run）。"""
    clean = _strip_markdown(text or "")[:_MAX_SPEAK_CHARS]
    if not clean:
        return None
    path = _out_path()
    try:
        await _run(clean, path)
    except Exception:  # noqa: BLE001 — 语音是增强能力，失败不阻塞对话
        logger.exception("tts synthesize failed")
        return None
    if path.exists() and path.stat().st_size > 0:
        return str(path)
    return None
