"""
责任判定规则（纯函数，无第三方依赖）。

基于 scene 事件/目标类型做规则式责任判定，
供 llm.py（mock 模式）与单元测试复用。
"""
from __future__ import annotations

from typing import Any

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


def _split_types(types: list[str]):
    motor_first = ["car", "truck", "bus"]
    mv = next((t for t in types if t in motor_first), "机动车")
    st = next((t for t in types if t not in motor_first), "另一方")
    return mv, st


def judge_from_scene(scene: dict) -> dict | None:
    """基于 scene 事件/目标类型判责，返回 None 表示无法从场景判责。"""
    if not scene:
        return None
    events = scene.get("events") or []
    vehicles = {v.get("id"): v for v in (scene.get("vehicles") or [])}
    participants = []
    for e in events:
        if e.get("type") == "collision":
            participants = e.get("participants") or []
            break
    if not participants:
        return None

    types = [vehicles.get(p, {}).get("type", "") for p in participants]
    if any(t == "pedestrian" for t in types):
        mv, st = _split_types(types)
        return {
            "responsibility": {"party_1": "primary", "party_2": "secondary", "split": "80/20"},
            "basis": ["《道交法》第47条第2款 机动车行经没有交通信号的道路遇行人横过道路应避让"],
            "reasoning": [f"{mv}为机动车未避让行人", f"{st}行人未尽注意义务"],
            "confidence": 0.7,
        }
    if any(t in ("motorcycle", "bicycle") for t in types):
        return {
            "responsibility": {"party_1": "primary", "party_2": "secondary", "split": "70/30"},
            "basis": ["《道交法》第47条 让行规定", "《实施条例》第51条"],
            "reasoning": ["机动车未让行非机动车", "非机动车方未尽注意义务"],
            "confidence": 0.65,
        }
    return None


def judge_text(scene_text: str) -> dict:
    """基于文字关键词判责（兜底）。"""
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


def judge(scene_text: str, evidence: Any, scene: dict | None = None) -> dict:
    """组合判责：场景优先，文字兜底。"""
    from_scene = judge_from_scene(scene)
    return from_scene or judge_text(scene_text)
