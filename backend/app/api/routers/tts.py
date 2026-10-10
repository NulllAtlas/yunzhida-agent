"""文本转语音接口（语音对话）：文本 → mp3 音频 URL。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.tts import synthesize_async

router = APIRouter(prefix="/api", tags=["tts"])


class TTSReq(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


@router.post("/tts")
async def tts(req: TTSReq) -> dict[str, Any]:
    """文本转语音：返回 /outputs/tts/ 下的音频 URL，供前端播放。"""
    path = await synthesize_async(req.text)
    if not path:
        return {"code": 1, "msg": "语音合成失败", "data": {"audio_url": ""}}
    name = Path(path).name
    return {"code": 0, "msg": "ok", "data": {"audio_url": f"/outputs/tts/{name}"}}
