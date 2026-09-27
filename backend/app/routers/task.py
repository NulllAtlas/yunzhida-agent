from fastapi import APIRouter, HTTPException
from app.store import store

router = APIRouter()


@router.get("/task/{task_id}")
async def get_task(task_id: str):
    task = store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "task_id": task["task_id"],
        "status": task["status"],
        "stage": task["stage"],
        "progress": task["progress"],
        "error": task["error"],
        "created_at": task["created_at"],
    }
