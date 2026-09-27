"""
LangGraph 构图。

数据流：
  START → perceive → retrieve → (judge ∥ respond) → aggregate → END

judge 与 respond 并行，等待两者都完成后进入 aggregate。
MVP 阶段使用简单的顺序函数；后续可升级为 StateGraph 并行分支。
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from app.graph.nodes import (
    aggregate_node,
    judge_node,
    perceive_node,
    respond_node,
    retrieve_node,
)
from app.graph.state import State


def build_graph():
    builder = StateGraph(State)
    builder.add_node("perceive", perceive_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("judge", judge_node)
    builder.add_node("respond", respond_node)
    builder.add_node("aggregate", aggregate_node)

    builder.set_entry_point("perceive")
    builder.add_edge("perceive", "retrieve")
    # MVP：顺序执行判定与应急（迭代阶段改造为并行）
    builder.add_edge("retrieve", "judge")
    builder.add_edge("judge", "respond")
    builder.add_edge("respond", "aggregate")
    builder.add_edge("aggregate", END)

    return builder.compile()


graph = build_graph()
