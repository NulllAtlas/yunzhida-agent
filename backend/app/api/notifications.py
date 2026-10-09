"""双端实时事件推送（B2）：案件创建 / 研判完成 / 研判失败时同时通知两端。

与 TaskManager 的**单任务**进度广播（progress.py）不同，这里是全局的案件事件流：
车主端按 owner_id 只收自己名下的案件，交警端收全部案件 —— 即"研判结果双端同步推送"。

进程内内存实现，单机演示足够；多实例部署需换成 Redis 之类的共享总线。
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator


class EventHub:
    """进程内事件总线（发后即忘，只推给在线订阅者）。

    可见性规则：
    - 交警（police）：可见全部事件；
    - 车主（owner）：只可见 owner_id 与本人账号一致的事件；
    - 匿名：保持连接但不接收任何事件（车主端未登录时不泄露他人案件）。
    """

    def __init__(self) -> None:
        self._subs: dict[int, tuple[asyncio.Queue[dict[str, Any]], str, str]] = {}
        self._next_id = 0

    def publish(self, event: dict[str, Any]) -> None:
        """广播一条案件事件；订阅者不可见时静默跳过。"""
        owner_id = event.get("owner_id") or ""
        for queue, role, username in list(self._subs.values()):
            if role == "police" or (username and username == owner_id):
                queue.put_nowait(event)

    async def subscribe(self, role: str, username: str) -> AsyncIterator[dict[str, Any]]:
        """订阅案件事件流（调用方负责在断开时结束迭代）。"""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._next_id += 1
        sub_id = self._next_id
        self._subs[sub_id] = (queue, role, username)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subs.pop(sub_id, None)

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)


event_hub = EventHub()