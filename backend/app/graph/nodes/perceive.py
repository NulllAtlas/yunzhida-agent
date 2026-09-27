from app.graph.state import RoadMindState
from app.schemas import Scene
from app.services.mock_data import build_mock_tracking_scene


async def perceive(state: RoadMindState) -> RoadMindState:
    """感知节点占位。D6 起调 P3 的 POST /perceive 得到真实 scene。"""
    scene = build_mock_tracking_scene()
    state["scene"] = Scene.model_validate(scene).model_dump()
    return state
