"""主流程 API 路由：上传/创建任务、查询状态、结果。"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.api.tasks import task_manager
from app.schemas.models import CaseInput, TaskInfo

router = APIRouter(prefix="/api", tags=["cases"])


@router.post("/cases", response_model=TaskInfo)
async def create_case(case: CaseInput, background: BackgroundTasks):
    """创建案件并启动多智能体分析。MVP 阶段用文字描述驱动。"""
    task = task_manager.create()
    # 组合输入文本（文字描述优先，后续接视频/照片文件上传）
    text = case.text_description or "路口两车发生碰撞，疑似追尾"
    background.add_task(task_manager.run, task, text)
    return task


@router.get("/tasks/{task_id}/status", response_model=TaskInfo)
async def get_status(task_id: str):
    task = task_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.get("/tasks/{task_id}/result", response_model=TaskInfo)
async def get_result(task_id: str):
    task = task_manager.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    if task.status not in ("done", "failed"):
        raise HTTPException(status_code=202, detail="task still processing")
    return task
