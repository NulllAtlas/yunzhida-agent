from app.graph.state import RoadMindState


async def aggregate(state: RoadMindState) -> RoadMindState:
    """汇聚节点占位：校验输出完整性，标记失败。"""
    if not state.get("scene") or not state.get("judgment") or not state.get("response"):
        state["error"] = "结果不完整"
    return state
