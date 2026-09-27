import time
from typing import List, Dict, Any

from app.config import get_settings


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def call(self, messages: List[Dict[str, Any]], temperature: float = 0.2) -> str:
        """调用 MoMA LLM 网关的占位实现。骨架阶段返回空/模拟文本。

        集成点（D3 起）：向 self.settings.moma_base_url 发起请求，
        携带 Authorization 与 messages，含超时与重试。
        """
        return ""
