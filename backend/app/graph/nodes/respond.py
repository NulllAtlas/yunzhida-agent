from app.graph.state import RoadMindState
from app.schemas import Scene, Judgment, ResponsePlan
from app.services import respond as respond_service


async def respond(state: RoadMindState) -> RoadMindState:
    scene = Scene.model_validate(state["scene"])
    judgment = Judgment.model_validate(state["judgment"])
    plan: ResponsePlan = await respond_service.respond(scene, judgment)
    state["response"] = plan.model_dump()
    return state
