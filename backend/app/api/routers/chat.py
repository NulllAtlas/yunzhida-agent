"""对话 API（Streamlit 界面用）：多轮对话透传 MoMA LLM。"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.llm import llm_service

router = APIRouter(prefix="/api", tags=["chat"])

_SYSTEM_PROMPT = (
    "你是 RoadMind 交通事故智能研判助手，帮助用户解答交通事故处理、责任判定、"
    "应急处理、保险理赔等相关问题。提问的用户多为刚经历事故的车主，情绪可能紧张不安，"
    "回答的第一句必须是一句安抚语（如「别担心，先确认人和车都安全，我来帮你梳理」），"
    "之后再给专业建议；整体语气温和、给人安全感，避免冷冰冰的公文腔。"
    "用户常常分多条消息补充信息（先说一半再补一句），务必把此前几条消息"
    "**整合在一起理解**，不要把每条当成孤立的新问题；回答时引用此前已提供"
    "的关键信息（如姓名、事故经过、已确认的细节），体现你记得之前聊过的内容。"
    "回答简洁专业，使用中文；涉及法条时引用《道路交通安全法》/《实施条例》具体条款；"
    "涉及责任认定时提醒：智能研判仅供参考，最终以交管部门认定为准。"
)

# 安抚开头兜底：LLM 对 system prompt 的遵循不稳定，回复没带安抚语时前置一句
_COMFORT_RE = re.compile(r"别担心|别慌|别着急|先确认|安全第一|人在就好|深呼吸|先别")
_COMFORT_LINE = "别担心，先确认人和车都安全，我来帮你梳理。\n\n"


class ChatMessage(BaseModel):
    role: str = "user"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)


@router.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    """多轮对话：历史消息透传 MoMA LLM（保留最近 20 条，控制上下文长度）。"""
    history = [m for m in req.messages if m.content.strip()][-20:]
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}] + [
        {"role": m.role, "content": m.content} for m in history
    ]
    try:
        reply = await llm_service.call_chat(messages, temperature=0.3)
    except Exception:  # noqa: BLE001 — 网关异常返回友好提示
        reply = "抱歉，研判服务暂时不可用，请稍后重试。"
    # 安抚开头兜底：LLM 没按 system prompt 以安抚语开头时，前置一句保证语气统一
    if not _COMFORT_RE.search(reply[:60]):
        reply = _COMFORT_LINE + reply
    return {"code": 0, "msg": "ok", "data": {"reply": reply}}
