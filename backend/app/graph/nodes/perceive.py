"""M1 感知节点：视频/文字 → scene。"""
from __future__ import annotations

from app.graph.state import State
from app.services.perception import perception_service


async def perceive_node(state: State) -> State:
    state["step"] = "perceiving"
    state["scene"] = await perception_service.perceive(
        state.get("case_id", "case"), state.get("input_text")
    )
    return state
