"""Graph wiring.

The route is fixed while there is a single scenario; LLM-driven routing comes when several
scenarios exist and the next step stops being obvious. Runs are checkpointed to Redis because the
approval step pauses the graph, and a pause that does not survive a restart is not an approval.
"""

import os

from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from alerts import AlertEvent
from graph.approval_agent import approval, execute
from graph.diagnose_agent import diagnose_node
from graph.monitor_agent import monitor
from graph.state import AIOpsState
from intent.classifier import Intent
from safety.hitl import Decision

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

_graph = None


def build_graph(checkpointer):
    graph = StateGraph(AIOpsState)
    graph.add_node("monitor", monitor)
    graph.add_node("diagnose", diagnose_node)
    graph.add_node("approval", approval)
    graph.add_node("execute", execute)
    graph.add_edge(START, "monitor")
    graph.add_edge("monitor", "diagnose")
    graph.add_edge("diagnose", "approval")
    graph.add_edge("approval", "execute")
    graph.add_edge("execute", END)
    return graph.compile(checkpointer=checkpointer)


async def get_graph():
    global _graph
    if _graph is None:
        saver = AsyncRedisSaver(REDIS_URL)
        await saver.asetup()
        _graph = build_graph(saver)
    return _graph


def _config(incident_id: str) -> dict:
    return {"configurable": {"thread_id": incident_id}}


def is_awaiting_approval(state: dict) -> bool:
    return bool(state.get("__interrupt__"))


async def run(event: AlertEvent, intent: Intent, incident_id: str) -> AIOpsState:
    graph = await get_graph()
    return await graph.ainvoke(
        {
            "event": event.model_dump(mode="json"),
            "intent": intent.model_dump(mode="json"),
            "incident_id": incident_id,
        },
        config=_config(incident_id),
    )


async def resume(incident_id: str, decision: Decision) -> AIOpsState:
    """Continue a run that is paused at the approval step."""
    graph = await get_graph()
    return await graph.ainvoke(Command(resume=decision.model_dump(mode="json")), config=_config(incident_id))
