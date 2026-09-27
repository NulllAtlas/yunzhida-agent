from app.graph.state import RoadMindState
from app.schemas import Scene, Judgment
from app.services.rag import RAGService
from app.services import judge as judge_service


async def judge(state: RoadMindState) -> RoadMindState:
    scene = Scene.model_validate(state["scene"])
    rag_service = RAGService()
    retrieved = await rag_service.retrieve(scene.scene_factors.road_type)
    state["retrieved"] = retrieved
    judgment: Judgment = await judge_service.judge(scene, retrieved)
    state["judgment"] = judgment.model_dump()
    return state
