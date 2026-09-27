import asyncio
import os

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.store import store, run_task

router = APIRouter()


class UploadResp(BaseModel):
    task_id: str
    status: str


@router.post("/upload", response_model=UploadResp, status_code=202)
async def upload(file: UploadFile = File(...), role: str = "owner"):
    settings = get_settings()
    os.makedirs(settings.upload_dir, exist_ok=True)
    task_id = store.create()
    dest = os.path.join(settings.upload_dir, f"{task_id}_{file.filename or 'video.mp4'}")
    with open(dest, "wb") as f:
        f.write(await file.read())
    asyncio.create_task(run_task(task_id))
    return UploadResp(task_id=task_id, status="pending")
