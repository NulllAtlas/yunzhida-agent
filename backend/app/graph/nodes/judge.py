"""M3 判定节点：scene + 检索 → judgment。"""
from __future__ import annotations

from app.core.config import settings
from app.graph.state import State
from app.schemas.models import Judgment, Responsibility
from app.services.llm import llm_service


async def judge_node(state: State) -> State:
    state["step"] = "judging"
    text = state.get("input_text", "")
    scene = state.get("scene")
    scene_text = text or (f"{scene.road} {' '.join(e.type for e in scene.events)}" if scene else "")

    raw = await llm_service.judge(scene_text, state.get("retrieved"))
    state["judgment"] = Judgment(
        scene_id=state.get("case_id", "case"),
        responsibility=Responsibility(**raw["responsibility"]),
        basis=raw["basis"],
        reasoning=raw["reasoning"],
        confidence=raw["confidence"],
    )
    return state
