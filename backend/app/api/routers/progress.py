"""进度推送路由（D4/D5）：WebSocket 实时推送任务各阶段进度与结果。

连接：`ws://localhost:8000/api/ws/tasks/{task_id}`
事件：`{"type": "progress|done|failed|status", "step": "...", "status": "...", "progress": 0.6}`
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.tasks import task_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ws", tags=["progress"])


@router.websocket("/tasks/{task_id}")
async def task_progress(websocket: WebSocket, task_id: str) -> None:
    await websocket.accept()
    if task_manager.get(task_id) is None:
        await websocket.send_json({"type": "error", "status": "not_found", "msg": "task not found"})
        await websocket.close(code=4404)
        return
    try:
        async for event in task_manager.subscribe(task_id):
            await websocket.send_json(event)
    except WebSocketDisconnect:
        logger.info("ws client disconnected: %s", task_id)
    finally:
        try:
            await websocket.close()
        except RuntimeError:  # 已关闭
            pass