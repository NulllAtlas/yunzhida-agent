"""主流程 API 路由（D1/D2/D7）：创建案件、查询状态、查询结果。"""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from app.api.tasks import task_manager
from app.core.errors import ApiError
from app.schemas.models import CaseInput, TaskInfo

router = APIRouter(prefix="/api", tags=["cases"])


@router.post("/cases", response_model=TaskInfo, status_code=202)
async def create_case(case: CaseInput, background: BackgroundTasks) -> TaskInfo:
    """创建案件并启动多智能体分析（异步，立即返回 pending 状态）。"""
    text = (case.text_description or "").strip()
    if not (case.video_id or case.scene_id or text):
        raise ApiError(
            "EMPTY_INPUT",
            "请至少提供 video_id / scene_id / text_description 之一",
            422,
        )
    task = task_manager.create(input_text=text)
    background.add_task(task_manager.run, task, text or "路口两车发生碰撞，疑似追尾")
    return task


@router.get("/tasks/{task_id}/status", response_model=TaskInfo)
async def get_status(task_id: str) -> TaskInfo:
    task = task_manager.get(task_id)
    if not task:
        raise ApiError("TASK_NOT_FOUND", "任务不存在", 404)
    return task


@router.get("/tasks/{task_id}/result", response_model=TaskInfo)
async def get_result(task_id: str) -> TaskInfo:
    task = task_manager.get(task_id)
    if not task:
        raise ApiError("TASK_NOT_FOUND", "任务不存在", 404)
    if task.status not in ("done", "failed"):
        raise ApiError("TASK_PROCESSING", "任务仍在处理中", 202)
    return task


@router.get("/metrics")
async def metrics() -> dict:
    """运行指标（D8）：任务计数与并发水位。"""
    return {
        "code": 0,
        "msg": "ok",
        "data": {**task_manager.metrics, "tasks_total": len(task_manager.list_task_ids())},
    }