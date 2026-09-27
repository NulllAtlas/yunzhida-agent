from typing import Any, Dict, List, TypedDict


class RoadMindState(TypedDict, total=False):
    task_id: str
    scene: Dict[str, Any]
    retrieved: List[Dict[str, Any]]
    judgment: Dict[str, Any]
    response: Dict[str, Any]
    error: str
