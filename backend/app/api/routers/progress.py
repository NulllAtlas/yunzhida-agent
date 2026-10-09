"""进度推送路由（D4/D5）：WebSocket 实时推送任务各阶段进度与结果。

连接：`ws://localhost:8000/api/ws/tasks/{task_id}`
事件：`{"type": "progress|done|failed|status", "step": "...", "status": "...", "progress": 0.6}`

另含双端案件事件流（B2）：
连接：`ws://localhost:8000/api/ws/notifications?token=<JWT>`
事件：`{"type": "case_created|case_done|case_failed", "task_id": "...", "owner_id": "..."}`
交警令牌收到全部案件；车主令牌只收 owner_id 与本人一致的事件；匿名不接收。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.notifications import event_hub
from app.api.tasks import task_manager
from app.core.security import decode_token

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


@router.websocket("/notifications")
async def case_notifications(websocket: WebSocket, token: str = Query("")) -> None:
    """双端案件事件流（B2）：车主收自己名下案件，交警收全部案件。"""
    await websocket.accept()
    user = decode_token(token)
    role = user["role"] if user else "anonymous"
    username = user["username"] if user else ""
    try:
        async for event in event_hub.subscribe(role, username):
            await websocket.send_json(event)
    except WebSocketDisconnect:
        logger.info("ws notifications disconnected: role=%s user=%s", role, username)
    finally:
        try:
            await websocket.close()
        except RuntimeError:  # 已关闭
            pass