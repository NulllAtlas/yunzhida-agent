"""
LangGraph 构图。

数据流：
  START → perceive → retrieve → accident_gate → (judge ∥ respond) → aggregate → END

accident_gate 把确定性事故门槛算成公共结论后，judge（事后责任）与 respond（当下处置）
fan-out 并行执行，等待两者都完成后进入 aggregate。两条分支互不读写对方的结果，
因此并行不会改变各自输出。
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from app.graph.nodes import (
    aggregate_node,
    gate_node,
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
    # 节点名不能与 state 键（gate）重名，LangGraph 会直接报错
    builder.add_node("accident_gate", gate_node)
    builder.add_node("judge", judge_node)
    builder.add_node("respond", respond_node)
    builder.add_node("aggregate", aggregate_node)

    builder.set_entry_point("perceive")
    builder.add_edge("perceive", "retrieve")
    builder.add_edge("retrieve", "accident_gate")
    # accident_gate 之后 fan-out：judge 与 respond 并行
    builder.add_edge("accident_gate", "judge")
    builder.add_edge("accident_gate", "respond")
    builder.add_edge("judge", "aggregate")
    builder.add_edge("respond", "aggregate")
    builder.add_edge("aggregate", END)

    return builder.compile()


graph = build_graph()
