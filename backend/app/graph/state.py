"""
LangGraph 共享状态（State Schema）。

对应文档《TEAM-ROLES.md》与《ARCHITECTURE.md》设计。
"""
from __future__ import annotations

from typing import Annotated, Optional, TypedDict

from app.schemas.models import (
    EmergencyResponse,
    Judgment,
    RetrievedDoc,
    Scene,
)


class RoadMindState(TypedDict, total=False):
    """多智能体共享状态，各节点读写同一状态对象。"""

    case_id: str
    input_text: str

    # M1 感知结果
    scene: Optional[Scene]
    # M2 检索增强
    retrieved: list[RetrievedDoc]
    # M3 判定结果
    judgment: Optional[Judgment]
    # M4 应急结果
    response: Optional[EmergencyResponse]

    # 汇聚结果（给前端）
    result: dict

    # 内部进度/错误
    step: str
    error: Optional[str]


# 便捷类型别名
State = RoadMindState
