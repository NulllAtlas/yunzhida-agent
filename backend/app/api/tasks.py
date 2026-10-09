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
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from app.api.notifications import event_hub
from app.core.config import settings
from app.core.db import (
    get_flow_status,
    insert_timeline,
    needs_pre_review_advance,
    set_case_flow_status,
    upsert_case,
)
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
    "aggregating": ("aggregating", 0.9),
    "done": ("done", 1.0),
}

# 节点名 → 阶段。节点**开始执行**时即可推送，不必等它跑完。
_NODE_STEP: dict[str, str] = {
    "perceive": "perceiving",
    "retrieve": "retrieving",
    "judge": "judging",
    "respond": "responding",
    "aggregate": "aggregating",
}

_TERMINAL = ("done", "failed")


class TaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskInfo] = {}
        self._input_texts: dict[str, str] = {}
        self._media_paths: dict[str, str | None] = {}
        self._filenames: dict[str, str] = {}
        self._photo_paths: dict[str, list[str]] = {}
        # 案件与车主绑定 + 业务状态机起始态（B2/B4），随任务创建时一起登记
        self._owners: dict[str, str] = {}
        self._flow_init: dict[str, str] = {}
        self._subscribers: dict[str, set[asyncio.Queue[dict]]] = {}
        # 持有后台任务的强引用：asyncio 只保存弱引用，create_task 的返回值若无人接管，
        # 任务可能在执行途中被 GC 回收，"任务莫名消失/卡住"就是这么来的。
        self._bg_tasks: set[asyncio.Task] = set()
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)
        # 指标（D8）
        self.metrics: dict[str, int] = {"created": 0, "running": 0, "done": 0, "failed": 0}

    # ---------- 状态 ----------

    def create(self, input_text: str = "", media_path: str | None = None,
               filename: str = "", photo_paths: list[str] | None = None,
               owner_id: str = "", flow_status: str = "submitted") -> TaskInfo:
        task = TaskInfo(task_id=uuid.uuid4().hex[:12])
        self._tasks[task.task_id] = task
        self.metrics["created"] += 1
        self._input_texts[task.task_id] = input_text
        self._media_paths[task.task_id] = media_path
        # 记下原始文件名，落库后车主端列表才能显示"哪一次提交"
        self._filenames[task.task_id] = filename
        # 随附现场照片（落库用；感知节点从 state 里拿的是同一份）
        self._photo_paths[task.task_id] = list(photo_paths or [])
        # 登录车主提交的案件绑定到账号（B2）；自动取证入口以 forensics 为起始态（B4）
        self._owners[task.task_id] = owner_id
        self._flow_init[task.task_id] = flow_status
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

    async def run(self, task_info: TaskInfo, input_text: str,
                  media_path: str | None = None,
                  photo_paths: list[str] | None = None) -> TaskInfo:
        """把任务丢到后台协程执行，立即返回（HTTP 不阻塞）。

        任务完成后由回调从 _bg_tasks 移除，避免强引用集合无限增长。
        """
        task = asyncio.create_task(
            self._work(task_info, input_text, media_path, photo_paths)
        )
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task_info

    async def run_blocking(self, task_info: TaskInfo, input_text: str,
                           media_path: str | None = None,
                           photo_paths: list[str] | None = None) -> TaskInfo:
        """同步执行（测试与一次性调用用）。"""
        await self._work(task_info, input_text, media_path, photo_paths)
        return task_info

    async def _work(self, task_info: TaskInfo, input_text: str,
                    media_path: str | None = None,
                    photo_paths: list[str] | None = None) -> None:
        # 照片路径是落盘之后才拿到的（create 时文件还没写），而落库读的是内部字典，
        # 所以这里补登记一次，否则记录列表里 photos 永远是空的。
        # 落库存**文件名**而不是绝对路径：接口会把这一列原样返回给前端，
        # 不该把部署机器上的目录结构泄出去。
        if photo_paths is not None:
            self._photo_paths[task_info.task_id] = [
                Path(p).name for p in photo_paths
            ]
        async with self._semaphore:
            self.metrics["running"] += 1
            try:
                await asyncio.wait_for(
                    self._stream_graph(task_info, input_text, media_path, photo_paths),
                    timeout=settings.task_timeout_s,
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

    async def _stream_graph(self, task_info: TaskInfo, input_text: str,
                            media_path: str | None = None,
                            photo_paths: list[str] | None = None) -> None:
        """消费 LangGraph 事件流，实时更新阶段与进度。

        用 astream_events 而不是 astream(stream_mode="values")：后者的状态快照
        只在节点**跑完之后**才产生，于是判定节点里那次最耗时的 LLM 调用期间，
        进度会一直停在上一阶段不动。astream_events 的 on_chain_start 在节点
        执行**前**触发，进度条才能真正跟着走。
        """
        state: State = {
            "case_id": task_info.task_id,
            "input_text": input_text,
            "media_path": media_path,
            "photo_paths": list(photo_paths or []),
            "step": "pending",
        }
        result: dict[str, Any] | None = None
        async for event in graph.astream_events(state, version="v2"):
            kind, name = event["event"], event.get("name")
            if kind == "on_chain_start" and name in _NODE_STEP:
                step = _NODE_STEP[name]
                status, progress = _STEP_MAP.get(
                    step, (task_info.status, task_info.progress)
                )
                task_info.status = status
                task_info.progress = progress
                self._publish(
                    task_info.task_id,
                    {"type": "progress", "step": step, "status": status, "progress": progress},
                )
            elif kind == "on_chain_end" and name == "perceive":
                # 感知节点跑完：关键帧此刻已生成（标注了事故车辆识别框），
                # 立刻挂到任务状态并广播 —— 对话框/前端不用等任务 done 就能反馈关键帧片段
                self._collect_keyframes(task_info, event)
            elif kind == "on_chain_end" and name == "LangGraph":
                # 根链的 output 即最终 state
                output = event["data"].get("output")
                if isinstance(output, dict):
                    result = output.get("result")

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

    def _collect_keyframes(self, task_info: TaskInfo, event: dict) -> None:
        """从感知节点的输出 state 里提取关键帧，挂到任务状态并广播。

        兼容 scene 为 Pydantic 对象 / dict 两种形态（LangGraph 的 output
        在内存里是对象，跨进程/序列化后是 dict）；拿不到就跳过，不影响主流程。
        """
        try:
            output = event["data"].get("output")
            scene = output.get("scene") if isinstance(output, dict) else None
            if scene is None:
                return
            events = scene.get("events") if isinstance(scene, dict) else scene.events
            kfs = [
                ev.get("keyframe") if isinstance(ev, dict) else ev.keyframe
                for ev in events or []
            ]
            kfs = [k for k in kfs if k]
            if kfs:
                task_info.keyframes = kfs
                self._publish(
                    task_info.task_id,
                    {"type": "keyframes", "keyframes": kfs},
                )
        except Exception:  # noqa: BLE001 — 关键帧是展示增强，不能阻塞主流程
            logger.exception("collect keyframes failed for task %s", task_info.task_id)

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
        task_id = task_info.task_id
        owner_id = self._owners.get(task_id, "")
        try:
            upsert_case(
                task_id=task_id,
                case_id=task_id,
                status=task_info.status,
                input_text=self._input_texts.get(task_id, ""),
                filename=self._filenames.get(task_id, ""),
                photos=self._photo_paths.get(task_id, []),
                result=result if result is not None else self._result_dump(task_info),
                error=task_info.error,
                owner_id=owner_id,
                flow_status=self._flow_init.get(task_id, "submitted"),
            )
            # 双端联动：案件创建时记初始事件；分析完成后自动推进到"待交警受理"。
            # 自动取证入口（B4）起始态是 forensics，标题随起始态走。
            if task_info.status == "pending":
                flow_init = self._flow_init.get(task_id, "submitted")
                if flow_init == "forensics":
                    insert_timeline(
                        task_id, "status", "行车记录仪自动取证",
                        "事故触发，已自动调取事发前片段，进入 AI 研判",
                    )
                else:
                    insert_timeline(
                        task_id, "status", "案件已提交",
                        "车主已提交事故材料，等待 AI 研判",
                    )
            elif task_info.status == "done" and needs_pre_review_advance(task_id):
                set_case_flow_status(
                    task_id, "pending_review",
                    note="AI 多智能体研判完成，已进入交警受理队列",
                )
        except Exception:  # noqa: BLE001
            logger.exception("persist task %s failed", task_id)

        # 双端同步推送（B2）：研判结果同时送达车主端与交警端。
        # 推送失败绝不能影响主流程，单独兜一层异常。
        try:
            event = {
                "task_id": task_id,
                "owner_id": owner_id,
                "status": task_info.status,
                "filename": self._filenames.get(task_id, ""),
                "input_text": self._input_texts.get(task_id, ""),
                "flow_status": get_flow_status(task_id),
            }
            if task_info.status == "pending":
                event["type"] = "case_created"
            elif task_info.status == "done":
                event["type"] = "case_done"
                event["result"] = self._result_dump(task_info)
            elif task_info.status == "failed":
                event["type"] = "case_failed"
                event["error"] = task_info.error
            else:
                return
            event_hub.publish(event)
        except Exception:  # noqa: BLE001
            logger.exception("publish event for task %s failed", task_id)


task_manager = TaskManager()