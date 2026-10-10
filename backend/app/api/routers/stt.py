"""语音输入接口（STT）：麦克风录音文件 → 中文文字。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, UploadFile

from app.services.stt import transcribe

router = APIRouter(prefix="/api", tags=["stt"])


@router.post("/stt")
async def stt(audio: UploadFile = File(...)) -> dict[str, Any]:
    """语音转文字：接收录音（wav/mp3/m4a），返回识别出的中文文字。"""
    import tempfile
    from pathlib import Path

    data = await audio.read()
    if not data:
        return {"code": 1, "msg": "录音为空", "data": {"text": ""}}
    suffix = Path(audio.filename or "record.wav").suffix or ".wav"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data)
        tmp.close()
        text = transcribe(tmp.name)
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    if not text:
        return {"code": 1, "msg": "未能识别出内容", "data": {"text": ""}}
    return {"code": 0, "msg": "ok", "data": {"text": text}}
