from fastapi import APIRouter, HTTPException
from app.store import store

router = APIRouter()


@router.get("/result/{task_id}")
async def get_result(task_id: str):
    task = store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task["status"] != "done":
        return {"task_id": task_id, "status": task["status"], "stage": task["stage"], "progress": task["progress"]}
    return task["result"]
