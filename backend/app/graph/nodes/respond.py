"""M4 应急节点：scene → response。"""
from __future__ import annotations

from app.graph.state import State
from app.schemas.models import EmergencyResponse, ResponseStep
from app.services.llm import llm_service


async def respond_node(state: State) -> State:
    state["step"] = "responding"
    scene = state.get("scene")
    text = state.get("input_text", "")

    accident_type = "general"
    if scene:
        for e in scene.events:
            if e.type == "vehicle_pedestrian":
                accident_type = "vehicle_pedestrian"
                break
            if e.type == "rear_end":
                accident_type = "rear_end"
    if accident_type == "general" and "追尾" in text:
        accident_type = "rear_end"
    if accident_type == "general" and ("行人" in text or "撞人" in text):
        accident_type = "vehicle_pedestrian"

    raw = await llm_service.draft_response(accident_type)
    state["response"] = EmergencyResponse(
        scene_id=state.get("case_id", "case"),
        accident_type=accident_type,
        priority=raw["priority"],
        steps=[ResponseStep(**s) for s in raw["steps"]],
        insurance=raw["insurance"],
    )
    return state
