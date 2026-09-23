"""Graph wiring.

The route is fixed while there is a single scenario; LLM-driven routing comes when several
scenarios exist and the next step stops being obvious.
"""

from langgraph.graph import END, START, StateGraph

from alerts import AlertEvent
from graph.monitor_agent import monitor
from graph.state import AIOpsState
from intent.classifier import Intent


def build_graph():
    graph = StateGraph(AIOpsState)
    graph.add_node("monitor", monitor)
    graph.add_edge(START, "monitor")
    graph.add_edge("monitor", END)
    return graph.compile()


_graph = build_graph()


async def run(event: AlertEvent, intent: Intent) -> AIOpsState:
    return await _graph.ainvoke({"event": event, "intent": intent})
