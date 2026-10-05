"""
任务管理器（D2/D4/D5/D8）。

职责：
- 内存态任务状态（pending → perceiving → retrieving → judging → responding → done|failed）
- 阶段进度实时广播（供 WebSocket 订阅，D4/D5）
- 并发限流 + 单任务超时熔断（D8）
- 完成/失败后把结果落到 SQLite，供交警端案件列表与详情使用（D7）
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, AsyncIterator, Optional

from app.core.config import settings
from app.core.db import upsert_case
from app.graph.builder import graph
from app.graph.state import State
from app.schemas.models import AnalyzeResult, TaskInfo

logger = logging.getLogger(__name__)

# 各阶段对应的任务状态与进度占比
_STEP_MAP: dict[str, tuple[str, float]] = {
    "pending": ("pending", 0.0),
    "perceiving": ("perceiving", 0.2),
    "retrieving": ("retrieving", 0.4),
    "judging": ("judging", 0.6),
    "responding": ("responding", 0.8),
    "done": ("done", 1.0),
}

_TERMINAL = ("done", "failed")


class TaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskInfo] = {}
        self._input_texts: dict[str, str] = {}
        self._subscribers: dict[str, set[asyncio.Queue[dict]]] = {}
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)
        # 指标（D8）
        self.metrics: dict[str, int] = {"created": 0, "running": 0, "done": 0, "failed": 0}
        # D8：视频路径透传给感知节点做抽帧（避免参数在多层调用间扩散）
        self._video_paths: dict[str, str] = {}

    # ---------- 状态 ----------

    def create(self, input_text: str = "", video_path: str | None = None) -> TaskInfo:
        task = TaskInfo(task_id=uuid.uuid4().hex[:12])
        self._tasks[task.task_id] = task
        self.metrics["created"] += 1
        self._input_texts[task.task_id] = input_text
        if video_path:
            self._video_paths[task.task_id] = video_path
        self._persist(task, result=None)
        return task

    def get(self, task_id: str) -> Optional[TaskInfo]:
        return self._tasks.get(task_id)

    def list_task_ids(self) -> list[str]:
        return list(self._tasks)

    # ---------- 进度订阅（WS 用） ----------

    def _publish(self, task_id: str, event: dict) -> None:
        for queue in list(self._subscribers.get(task_id, ())):
            queue.put_nowait(event)

    async def subscribe(self, task_id: str) -> AsyncIterator[dict]:
        """订阅某任务的进度事件流，任务终态后自动结束。"""
        queue: asyncio.Queue[dict] = asyncio.Queue()
        self._subscribers.setdefault(task_id, set()).add(queue)
        try:
            task = self._tasks.get(task_id)
            if task is not None:
                yield {"type": "status", "status": task.status, "progress": task.progress,
                       "step": task.status}
                if task.status in _TERMINAL:
                    yield {"type": task.status, "status": task.status, "progress": task.progress,
                           "error": task.error, "result": self._result_dump(task)}
                    return
            while True:
                event = await queue.get()
                yield event
                if event.get("type") in _TERMINAL:
                    return
        finally:
            self._subscribers.get(task_id, set()).discard(queue)

    # ---------- 执行 ----------

    async def run(self, task_info: TaskInfo, input_text: str) -> TaskInfo:
        """把任务丢到后台协程执行，立即返回（HTTP 不阻塞）。"""
        asyncio.create_task(self._work(task_info, input_text))
        return task_info

    async def run_blocking(self, task_info: TaskInfo, input_text: str) -> TaskInfo:
        """同步执行（测试与一次性调用用）。"""
        await self._work(task_info, input_text)
        return task_info

    async def _work(self, task_info: TaskInfo, input_text: str) -> None:
        async with self._semaphore:
            self.metrics["running"] += 1
            try:
                await asyncio.wait_for(
                    self._stream_graph(task_info, input_text), timeout=settings.task_timeout_s
                )
                self.metrics["done"] += 1
                self._persist(task_info)
            except asyncio.TimeoutError:
                self._fail(task_info, f"任务超时（>{settings.task_timeout_s:.0f}s）已熔断")
                logger.warning("task %s timeout", task_info.task_id)
            except Exception as exc:  # noqa: BLE001
                self._fail(task_info, str(exc))
                logger.exception("task %s failed", task_info.task_id)
            finally:
                self.metrics["running"] -= 1
        return None

    async def _stream_graph(self, task_info: TaskInfo, input_text: str) -> None:
        """逐节点消费 LangGraph 状态流，实时更新阶段与进度。"""
        state: State = {
            "case_id": task_info.task_id,
            "input_text": input_text,
            "video_path": self._video_paths.get(task_info.task_id),
            "step": "pending",
        }
        snapshot: dict[str, Any] = {}
        async for snapshot in graph.astream(state, stream_mode="values"):
            step = str(snapshot.get("step") or "pending")
            status, progress = _STEP_MAP.get(step, (task_info.status, task_info.progress))
            task_info.status = status
            task_info.progress = progress
            self._publish(
                task_info.task_id,
                {"type": "progress", "step": step, "status": status, "progress": progress},
            )

        result = snapshot.get("result")
        if not result:
            raise RuntimeError("流水线未产出结果")
        task_info.result = AnalyzeResult(**result)
        task_info.status = "done"
        task_info.progress = 1.0
        self._publish(
            task_info.task_id,
            {"type": "done", "status": "done", "progress": 1.0, "result": self._result_dump(task_info)},
        )

    # ---------- 内部工具 ----------

    def _fail(self, task_info: TaskInfo, message: str) -> None:
        task_info.status = "failed"
        task_info.error = message
        self.metrics["failed"] += 1
        self._publish(
            task_info.task_id,
            {"type": "failed", "status": "failed", "progress": task_info.progress, "error": message},
        )
        self._persist(task_info)

    @staticmethod
    def _result_dump(task_info: TaskInfo) -> Optional[dict]:
        return task_info.result.model_dump() if task_info.result else None

    def _persist(self, task_info: TaskInfo, result: Optional[dict] = None) -> None:
        """结果落库；落库失败只记日志，不影响主流程。"""
        try:
            upsert_case(
                task_id=task_info.task_id,
                case_id=task_info.task_id,
                status=task_info.status,
                input_text=self._input_texts.get(task_info.task_id, ""),
                result=result if result is not None else self._result_dump(task_info),
                error=task_info.error,
            )
        except Exception:  # noqa: BLE001
            logger.exception("persist task %s failed", task_info.task_id)


task_manager = TaskManager()