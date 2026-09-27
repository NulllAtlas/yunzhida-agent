"""
LLM 网关服务。

MVP 阶段 use_mock=True 时返回确定性模板结果（保证全链路可跑）；
接入真实 MoMA/OpenAI 兼容网关后，use_mock=False 走真实调用。
"""
from __future__ import annotations

from typing import Any

from app.core.config import settings

# 责任判定 mock —— 基于关键要素做规则式判定，供 MVP 闭环演示
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


class LLMService:
    async def judge(self, scene_text: str, evidence: Any) -> dict:
        """责任判定。MVP 阶段做规则匹配，迭代阶段替换为 LLM 推理。"""
        if settings.use_mock:
            for rule in _RULE_JUDGMENTS:
                if any(k in scene_text for k in rule["match"]):
                    return {
                        "responsibility": rule["resp"],
                        "basis": rule["basis"],
                        "reasoning": rule["reasoning"],
                        "confidence": 0.8,
                    }
            return {
                "responsibility": {"party_1": "unknown", "party_2": "unknown", "split": ""},
                "basis": ["需补充现场要素"],
                "reasoning": ["要素不足，无法给出明确责任倾向"],
                "confidence": 0.3,
            }
        # TODO(迭代): 调用真实 LLM（MoMA 网关）
        raise NotImplementedError("真实 LLM 接入待实现")

    async def draft_response(self, accident_type: str) -> dict:
        """应急方案。MVP 阶段按事故类型返回模板。"""
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
