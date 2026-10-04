"""主流程 API 路由：上传/创建任务、查询状态、结果。"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.api.tasks import task_manager
from app.schemas.models import CaseInput, TaskInfo

router = APIRouter(prefix="/api", tags=["cases"])


@router.post("/cases", response_model=TaskInfo)
async def create_case(case: CaseInput, background: BackgroundTasks):
    """创建案件并启动多智能体分析。

    输入方式（至少一种）：
    - case.scene       直接喂入已检测的 scene 字典（跳过感知）
    - case.media_path  真实视频/照片检测（迭代阶段）
    - case.text_description  文字描述（兜底）
    """
    task = task_manager.create()
    text = case.text_description or "路口两车发生碰撞，疑似追尾"
    background.add_task(task_manager.run, task, text, case.scene, case.media_path)
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
