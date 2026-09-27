from langgraph.graph import StateGraph, END

from app.graph.state import RoadMindState
from app.graph.nodes import perceive, judge, respond, aggregate


def build_graph():
    g = StateGraph(RoadMindState)
    g.add_node("perceive", perceive.perceive)
    g.add_node("judge", judge.judge)
    g.add_node("respond", respond.respond)
    g.add_node("aggregate", aggregate.aggregate)
    g.set_entry_point("perceive")
    g.add_edge("perceive", "judge")
    g.add_edge("judge", "respond")
    g.add_edge("respond", "aggregate")
    g.add_edge("aggregate", END)
    return g.compile()
