"""
任务管理器：内存版任务状态存储 + 异步执行。

MVP 阶段使用内存字典存储任务；迭代阶段可替换为 Redis/队列。
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Optional

from app.graph.builder import graph
from app.graph.state import State
from app.schemas.models import AnalyzeResult, TaskInfo


class TaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskInfo] = {}

    def create(self) -> TaskInfo:
        task = TaskInfo(task_id=uuid.uuid4().hex[:12])
        self._tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> Optional[TaskInfo]:
        return self._tasks.get(task_id)

    async def run(self, task_info: TaskInfo, input_text: str) -> TaskInfo:
        """在事件循环后台执行多智能体流水线。"""
        async def _work():
            try:
                task_info.status = "perceiving"
                task_info.progress = 0.1
                state: State = {
                    "case_id": task_info.task_id,
                    "input_text": input_text,
                    "step": "pending",
                }
                final_state = await graph.ainvoke(state)
                task_info.status = "done"
                task_info.progress = 1.0
                task_info.result = AnalyzeResult(**final_state["result"])
            except Exception as exc:  # noqa: BLE001
                task_info.status = "failed"
                task_info.error = str(exc)

        asyncio.create_task(_work())
        return task_info


task_manager = TaskManager()
