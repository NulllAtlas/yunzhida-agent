"""汇聚节点：合并 scene/retrieved/judgment/response → result。"""
from __future__ import annotations

from app.graph.state import State


async def aggregate_node(state: State) -> State:
    state["step"] = "done"
    state["result"] = {
        "case_id": state.get("case_id", "case"),
        "scene": state.get("scene").model_dump() if state.get("scene") else None,
        "retrieved": [r.model_dump() for r in state.get("retrieved", [])],
        "judgment": state.get("judgment").model_dump() if state.get("judgment") else None,
        "response": state.get("response").model_dump() if state.get("response") else None,
    }
    return state
