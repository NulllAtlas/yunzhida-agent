"""对话 API：针对案件判定结果的多轮答疑（车主端聊天框）。

- 携带 `case_id` 时：从库中取该案件的判定结果注入 system 上下文，让 LLM 围绕结果作答；
- 多轮对话透传 MoMA LLM（保留最近 20 条，控制上下文长度）；
- `use_mock`/未配置网关时返回模板答疑（带上下文时）或原样回显（不带时），保证无凭据也能演示。
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.db import get_case
from app.services.llm import llm_service

router = APIRouter(prefix="/api", tags=["chat"])

_SYSTEM_PROMPT = (
    "你是云智达·交通事故智能研判助手，帮助用户解答交通事故处理、责任判定、"
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

_PARTY_LABEL = {
    "primary": "主要责任",
    "secondary": "次要责任",
    "equal": "同等责任",
    "none": "无责任",
    "unknown": "待补充认定",
}


class ChatMessage(BaseModel):
    role: str = "user"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    # 可选：把指定案件的判定结果作为答疑上下文注入
    case_id: str = Field("", max_length=64)


def _case_context(case_id: str) -> str:
    """把案件的判定结果整理成一段可注入的答疑上下文；查不到返回空串。"""
    case = get_case(case_id)
    if not case:
        return ""
    result = case.get("result") or {}
    judgment = result.get("judgment") or {}
    resp = judgment.get("responsibility") or {}
    split = resp.get("split") or "待定"
    return (
        f"当前正在答疑的案件判定结果如下（案件编号 {case.get('case_id') or case_id}，"
        f"业务状态：{case.get('flow_status') or 'submitted'}）：\n"
        f"- 事故类型：{judgment.get('accident_type') or '未知'}\n"
        f"- 责任划分：当事方一 {_PARTY_LABEL.get(resp.get('party_1'), '待补充')}；"
        f"当事方二 {_PARTY_LABEL.get(resp.get('party_2'), '待补充')}；责任比例 {split}\n"
        f"- 认定依据：{'；'.join(judgment.get('basis') or []) or '无'}\n"
        f"- 认定理由：{'；'.join(judgment.get('reasoning') or []) or '无'}\n"
        f"- 判定置信度：{round(float(judgment.get('confidence') or 0) * 100)}%\n"
        f"- 免责声明：{judgment.get('note') or '本结果为智能辅助研判建议，非最终裁定。'}\n"
        "车主是就上述判定结果提问，请围绕这份结论解释：责任划分的依据与逻辑、"
        "涉及法条的含义、对车主下一步（报警/保险/复议等）的建议。不要凭空编造该案件没有的信息。"
    )


def _mock_reply(case_context: str, question: str) -> str:
    """演示模式（未接模型）下的模板答疑；带案件上下文时给出结构化解答。"""
    if not case_context:
        return _COMFORT_LINE + (
            "（演示模式）我已收到你的问题。连接到真实大模型网关后，"
            "我可以针对具体案件与法条给出详细解答。"
        )

    def grab(key: str) -> str:
        m = re.search(rf"{re.escape(key)}[:：]\s*(.+)", case_context)
        return m.group(1).strip() if m else ""

    fault = grab("- 事故类型")
    resp = grab("- 责任划分")
    ratio = grab("责任比例")
    basis = grab("- 认定依据")
    reasons = grab("- 认定理由")
    conf = grab("- 判定置信度")

    lines = [
        "别担心，先确认人和车都安全，我来帮你梳理。",
        "",
        "根据系统对本案件的 AI 研判结论：",
    ]
    if fault:
        lines.append(f"· 事故类型：{fault}")
    if resp:
        lines.append(f"· 责任划分：{resp}")
    if ratio:
        lines.append(f"· 责任比例：{ratio}")
    if basis:
        lines.append(f"· 判定依据：{basis}")
    if reasons:
        lines.append(f"· 认定理由：{reasons}")
    if conf:
        lines.append(f"· 判定置信度：{conf}")
    lines += [
        "",
        "需要提示的是：该结论为智能辅助研判建议，最终以交管部门认定为准。",
        "如果对责任逻辑或下一步手续有疑问，可以继续问我。",
    ]
    return "\n".join(lines)


@router.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    """多轮对话：历史消息透传 MoMA LLM（保留最近 20 条，控制上下文长度）。"""
    history = [m for m in req.messages if m.content.strip()][-20:]
    context = _case_context(req.case_id) if req.case_id else ""
    system = _SYSTEM_PROMPT
    if context:
        system += "\n\n【当前案件判定结果上下文】\n" + context

    last_user = next((m.content for m in reversed(history) if m.role == "user"), "")
    if settings.use_mock or not settings.moma_base_url:
        reply = _mock_reply(context, last_user)
    else:
        # role 白名单过滤：直接调 API 可携带任意 role 字段，不滤的话
        # 能注入 role="system"/"developer" 的消息覆盖系统提示
        messages = [{"role": "system", "content": system}] + [
            {"role": m.role, "content": m.content}
            for m in history if m.role in ("user", "assistant")
        ]
        try:
            reply = await llm_service.call_chat(messages, temperature=0.3)
        except Exception:  # noqa: BLE001 — 网关异常返回友好提示
            reply = "抱歉，研判服务暂时不可用，请稍后重试。"

    # 安抚开头兜底：LLM 没按 system prompt 以安抚语开头时，前置一句保证语气统一
    if not _COMFORT_RE.search(reply[:60]):
        reply = _COMFORT_LINE + reply
    return {"code": 0, "msg": "ok", "data": {"reply": reply}}
