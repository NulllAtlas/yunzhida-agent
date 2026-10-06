"""视频上传路由（D1/D2）：接收视频文件安全落盘，返回可供创建案件使用的 video_id。

背景：早期只有 P4 联调占位 `POST /api/upload`（只收图片、固定返回），
没有任何接口把视频字节真正落盘；而 `POST /api/cases` 的 `video_id` 又要求
文件已存在于 `UPLOAD_DIR`。本路由补上「上传视频 → 落盘 → 建任务」缺失的一环。
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from app.core.config import settings
from app.core.errors import ApiError

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

# 允许的视频扩展名；按扩展名判定，兼容浏览器把 mp4 报成 application/octet-stream
_ALLOWED_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".m4v"}
_CHUNK = 1024 * 1024  # 分块读取，避免大视频一次性读入内存


@router.post("/video", status_code=201)
async def upload_video(file: UploadFile = File(...)) -> dict:
    """上传事故视频，落盘到 `UPLOAD_DIR`，返回 `video_id`。

    `video_id` 可直接用于 `POST /api/cases` 的 `video_id` 字段触发抽帧分析。
    """
    name = Path(file.filename or "").name
    ext = Path(name).suffix.lower()
    if not name or ext not in _ALLOWED_EXT:
        raise ApiError(
            "INVALID_FILE_TYPE",
            f"仅支持视频文件：{', '.join(sorted(_ALLOWED_EXT))}",
            422,
        )

    # 随机名落盘：避免覆盖同名文件，同时天然规避路径穿越
    safe_name = f"{uuid.uuid4().hex[:12]}{ext}"
    dest_dir = Path(settings.upload_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe_name

    limit = settings.max_upload_mb * 1024 * 1024
    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(_CHUNK):
                size += len(chunk)
                if size > limit:
                    raise ApiError(
                        "FILE_TOO_LARGE", f"视频超过 {settings.max_upload_mb}MB 限制", 413
                    )
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)  # 中途失败不留半个文件
        raise
    finally:
        await file.close()

    if size == 0:
        dest.unlink(missing_ok=True)
        raise ApiError("EMPTY_FILE", "上传文件为空", 422)

    return {
        "code": 0,
        "msg": "ok",
        "data": {"video_id": safe_name, "size": size, "content_type": file.content_type},
    }