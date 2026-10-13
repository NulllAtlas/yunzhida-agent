"""事故门控节点：把确定性门槛从 judge 内部提出来，作为判责与应急的公共前置。

提出来之后图结构变成

    perceive → retrieve → accident_gate → (judge ∥ respond) → aggregate

judge（事后责任）与 respond（当下处置）互不等待，但两者都消费 gate 的同一份结论，
不会出现"判责说非事故、应急却让你摆三角牌"的自相矛盾。
"""
from __future__ import annotations

from app.algo.accident_gate import resolve_gate
from app.graph.state import State


async def gate_node(state: State) -> State:
    state["step"] = "gating"
    # 传不含 gate 键的视图，强制按当前 scene 重算（本节点就是结论的来源）
    state["gate"] = resolve_gate({"scene": state.get("scene")})
    return state
