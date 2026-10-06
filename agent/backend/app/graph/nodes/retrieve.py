"""M2 检索节点：从场景/文字抽取查询词 → RAG 检索。"""
from __future__ import annotations

from app.graph.state import State
from app.services.rag import rag_service


async def retrieve_node(state: State) -> State:
    state["step"] = "retrieving"
    text = state.get("input_text", "")
    scene = state.get("scene")
    if scene and not text:
        text = f"碰撞 事故 {scene.road} {scene.traffic_light}"
    state["retrieved"] = rag_service.retrieve(text, top_k=4)
    return state
