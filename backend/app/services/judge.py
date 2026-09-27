from typing import List, Dict, Any

from app.schemas import Scene, Judgment, Verdict, Party, Law
from app.services import llm, rag


RULE_HINTS: Dict[str, List[str]] = {
    "rear_end": ["后车未保持安全距离", "前车无突然倒车等异常"],
    "car_pedestrian": ["人行横道未让行", "行人未遵守信号"],
}


async def judge(scene: Scene, retrieved: List[Dict[str, Any]]) -> Judgment:
    """责任判定（骨架实现）。D4 起拼接 scene + RAG 结果 → prompt → LLM 解析。"""
    has_collision = any(e.type in ("collision",) for e in scene.events)
    if not has_collision:
        return Judgment(confidence=0.3, low_confidence=True, needs_human_review=True)

    case_type = "rear_end"
    parties = [
        Party(object_id="obj_1", role="A", liability_pct=70, main_reason=RULE_HINTS["rear_end"][0]),
        Party(object_id="obj_2", role="B", liability_pct=30, main_reason=RULE_HINTS["rear_end"][1]),
    ]
    return Judgment(
        case_type=case_type,
        verdict=Verdict(parties=parties),
        reasoning=RULE_HINTS["rear_end"],
        laws=[Law(article="《道路交通安全法》第 43 条", summary="同车道追尾事故责任")],
        confidence=0.76,
        summary_text="A 车追尾 B 车，A 车负主要责任（70%）。",
    )
