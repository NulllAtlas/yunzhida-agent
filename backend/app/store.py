import asyncio
import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

from app.graph.builder import build_graph
from app.graph.state import RoadMindState

_graph = build_graph()


class TaskStore:
    def __init__(self) -> None:
        self._tasks: Dict[str, dict] = {}

    def create(self) -> str:
        task_id = f"t_{uuid.uuid4().hex[:8]}"
        self._tasks[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "stage": None,
            "progress": 0.0,
            "result": None,
            "error": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return task_id

    def get(self, task_id: str) -> Optional[dict]:
        return self._tasks.get(task_id)

    def set_stage(self, task_id: str, stage: str, progress: float) -> None:
        task = self._tasks.get(task_id)
        if task:
            task["stage"] = stage
            task["progress"] = progress
            task["status"] = "processing"

    def finish(self, task_id: str, result: dict) -> None:
        task = self._tasks.get(task_id)
        if task:
            task["status"] = "done"
            task["progress"] = 1.0
            task["result"] = result

    def fail(self, task_id: str, message: str) -> None:
        task = self._tasks.get(task_id)
        if task:
            task["status"] = "failed"
            task["error"] = message


store = TaskStore()


async def run_task(task_id: str) -> None:
    state: RoadMindState = {"task_id": task_id}
    stages = [
        ("perceive", 0.2),
        ("judge", 0.55),
        ("respond", 0.8),
        ("aggregate", 0.95),
    ]
    try:
        for stage, progress in stages:
            store.set_stage(task_id, stage, progress)
            state = await _graph.ainvoke(state)
        result = {
            "task_id": task_id,
            "scene": state["scene"],
            "judgment": state["judgment"],
            "response": state["response"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        store.finish(task_id, result)
    except Exception as exc:  # pragma: no cover
        store.fail(task_id, str(exc))
