"""
LLM 网关服务（M3/M4）。

- use_mock=True  时返回确定性模板结果（保证全链路可跑，无凭据也能演示）
- use_mock=False 时调用真实 MoMA 网关（OpenAI 兼容），统一 `call_chat`，
  带鉴权 / 超时 / 重试；判定结果按 JSON 解析并容错降级回规则匹配。
"""
from __future__ import annotations

import json
import re
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings

# 责任判定 mock —— 基于关键要素做规则式判定，供 MVP 闭环演示 / LLM 解析失败兜底
_RULE_JUDGMENTS = [
    {
        "match": ["追尾", "追尾", "follow"],
        "resp": {"party_1": "primary", "party_2": "none", "split": "100/0"},
        "basis": ["《道交法》第43条 同车道行驶后车应与前车保持安全距离"],
        "reasoning": ["后车未与前车保持足以采取紧急制动措施的安全距离", "前车无过错"],
    },
    {
        "match": ["变道", "变道", "lane"],
        "resp": {"party_1": "primary", "party_2": "none", "split": "100/0"},
        "basis": ["《实施条例》第44条 变更车道不得影响相关车道内正常行驶的机动车"],
        "reasoning": ["变道方未让行原车道正常行驶车辆"],
    },
    {
        "match": ["路口", "未让行", "intersection"],
        "resp": {"party_1": "primary", "party_2": "secondary", "split": "70/30"},
        "basis": ["《道交法》第47条 机动车行经路口应让行", "《实施条例》第51条 通过路口让行规定"],
        "reasoning": ["一方未按让行规则通行", "另一方未尽注意义务，承担次要责任"],
    },
]

_JUDGE_FALLBACK = {
    "responsibility": {"party_1": "unknown", "party_2": "unknown", "split": ""},
    "basis": ["需补充现场要素"],
    "reasoning": ["要素不足，无法给出明确责任倾向"],
    "confidence": 0.3,
}


def _rule_judge(scene_text: str) -> dict:
    """规则式兜底判定（mock 或 LLM 解析失败时使用）。"""
    for rule in _RULE_JUDGMENTS:
        if any(k in scene_text for k in rule["match"]):
            return {
                "responsibility": rule["resp"],
                "basis": rule["basis"],
                "reasoning": rule["reasoning"],
                "confidence": 0.8,
            }
    return dict(_JUDGE_FALLBACK)


class LLMService:
    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        """惰性构建 OpenAI 兼容客户端（指向 MoMA 网关）。"""
        if self._client is None:
            self._client = AsyncOpenAI(
                base_url=settings.moma_base_url or None,
                api_key=settings.moma_api_key or "not-set",
                timeout=60.0,
                max_retries=2,
            )
        return self._client

    async def call_chat(self, messages: list[dict], model: str | None = None) -> str:
        """调用 MoMA 网关，返回文本内容。

        use_mock 或未配置网关地址时走内置 mock 提示词拼接返回，
        保证不依赖网络也能演示。
        """
        model = model or settings.model_strong or "default"
        if settings.use_mock or not settings.moma_base_url:
            # mock：直接把最后一条 user 内容原样返回（由调用方处理），便于联调
            for m in reversed(messages):
                if m.get("role") == "user":
                    return str(m["content"])
            return ""
        resp = await self._get_client().chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
        )
        return (resp.choices[0].message.content or "").strip()

    async def judge(self, scene_text: str, evidence: Any) -> dict:
        """责任判定：优先真实 MoMA LLM，解析失败回退规则匹配。"""
        if settings.use_mock:
            return _rule_judge(scene_text)

        laws = ""
        if evidence:
            try:
                laws = "\n".join(f"- {d.get('title', '')}: {d.get('content', '')}" for d in evidence)
            except Exception:  # noqa: BLE001
                laws = ""
        prompt = (
            "你是一名专业的交通事故责任研判辅助助手。请根据事故描述与可引用的法规，"
            "给出责任认定结论，只输出 JSON，不要输出其它文字。JSON 结构：\n"
            '{"responsibility": {"party_1": "primary|secondary|equal|none|unknown", '
            '"party_2": "primary|secondary|equal|none|unknown", "split": "70/30"}, '
            '"basis": ["法条依据，可引用检索结果"], "reasoning": ["判定理由分条"], '
            '"confidence": 0.0到1.0之间的数字}\n\n'
            f"事故描述：{scene_text}\n\n可引用法规/案例：\n{laws}"
        )
        try:
            raw = await self.call_chat([{"role": "user", "content": prompt}])
            return self._parse_judgment(raw) or _rule_judge(scene_text)
        except Exception:  # noqa: BLE001  — 网络/鉴权/解析失败均回退规则
            return _rule_judge(scene_text)

    def _parse_judgment(self, text: str) -> dict | None:
        """从 LLM 输出中稳健提取 JSON，字段缺失时回退 None。"""
        if not text:
            return None
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        resp = data.get("responsibility") or {}
        party_1 = resp.get("party_1") or "unknown"
        party_2 = resp.get("party_2") or "unknown"
        if party_1 not in ("primary", "secondary", "equal", "none", "unknown"):
            party_1 = "unknown"
        if party_2 not in ("primary", "secondary", "equal", "none", "unknown"):
            party_2 = "unknown"
        try:
            confidence = float(data.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        return {
            "responsibility": {"party_1": party_1, "party_2": party_2, "split": str(resp.get("split") or "")},
            "basis": [str(b) for b in (data.get("basis") or [])],
            "reasoning": [str(r) for r in (data.get("reasoning") or [])],
            "confidence": confidence,
        }

    async def draft_response(self, accident_type: str) -> dict:
        """应急方案。MVP 阶段按事故类型返回模板（保持原样）。"""
        templates = {
            "vehicle_pedestrian": {
                "priority": 1,
                "steps": [
                    {"order": 1, "action": "立即开启双闪，停车熄火", "urgent": True},
                    {"order": 2, "action": "拨打 120 急救，说明伤员情况", "urgent": True},
                    {"order": 3, "action": "拨打 122/110 报警", "urgent": True},
                    {"order": 4, "action": "放置三角警示牌（来车方向 50 米）", "urgent": True},
                    {"order": 5, "action": "保护现场，勿移动伤员，等待救援", "urgent": True},
                ],
                "insurance": "同步拨打保险公司报案，拍摄现场照片与全景视频，保留证据。",
            },
            "rear_end": {
                "priority": 2,
                "steps": [
                    {"order": 1, "action": "开启双闪，停车熄火", "urgent": True},
                    {"order": 2, "action": "放置三角警示牌（来车方向 50 米）", "urgent": True},
                    {"order": 3, "action": "人员撤至安全地带，勿留在车道", "urgent": True},
                    {"order": 4, "action": "无伤亡可先拍照固定证据后撤离至安全处协商", "urgent": False},
                ],
                "insurance": "拨打保险报案，保留现场照片与行车记录仪。",
            },
        }
        return templates.get(
            accident_type,
            {
                "priority": 2,
                "steps": [
                    {"order": 1, "action": "开启双闪，停车熄火", "urgent": True},
                    {"order": 2, "action": "放置三角警示牌", "urgent": True},
                    {"order": 3, "action": "人员撤至安全地带", "urgent": True},
                    {"order": 4, "action": "有伤亡拨打 120，报警 122/110", "urgent": True},
                ],
                "insurance": "保留现场证据，及时报保险。",
            },
        )


llm_service = LLMService()
