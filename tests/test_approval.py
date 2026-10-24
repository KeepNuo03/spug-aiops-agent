from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from diagnosis.models import CulpritProcess, RemediationAction, VerifiedDiagnosis
from diagnosis.verify_outcome import Outcome
from graph import approval_agent
from graph.approval_agent import execute
from incidents import store
from intent.classifier import Intent
from safety.hitl import Decision, build_request

EVIDENCE = [{"probe": "top_processes", "tool": "exec_command", "result": {"command": "ps", "output": "344 stress-ng"}}]


def diagnosis(**overrides):
    defaults = dict(
        root_cause="stress-ng saturates the cpu",
        summary="four workers pin the cpu",
        confidence=0.95,
        evidence_used=["top_processes"],
        culprit_process=CulpritProcess(name="stress-ng", pid=344),
        actions=[RemediationAction(action="kill", pid=344, reason="stop it")],
        verified=True,
    )
    return VerifiedDiagnosis(**{**defaults, **overrides})


@pytest_asyncio.fixture
async def incident(database, make_event):
    record = await store.open(make_event())
    await store.update(record.id, event="awaiting approval", status="awaiting_approval")
    return record


@pytest.fixture
def executed(monkeypatch):
    calls = []

    async def fake_call_tool(name, arguments):
        calls.append((name, arguments))
        return {"host": arguments["host"], "command": "kill -TERM 344", "exit_status": 0, "output": ""}

    async def fake_verify(host, **kwargs):
        return Outcome(recovered=True, cpu_percent=0.3, detail="cpu is 0.3%, back under the 80% threshold")

    monkeypatch.setattr(approval_agent, "call_tool", fake_call_tool)
    monkeypatch.setattr(approval_agent, "verify_recovery", fake_verify)
    return calls


def state_for(incident, decision, actions=None):
    request = build_request(incident.id, "lab-host", "cause", actions or diagnosis().actions, "344 stress-ng")
    return {
        "event": None,
        "incident_id": incident.id,
        "intent": Intent(name="cpu_high", confidence=0.95, matched_by="label", entities={"hostname": "lab-host"}),
        "evidence": EVIDENCE,
        "diagnosis": diagnosis(),
        "approval": request,
        "decision": decision,
    }


async def test_approval_runs_the_rendered_command(incident, executed, make_event):
    state = state_for(incident, Decision(decision="approve", action_index=0))
    state["event"] = make_event()
    result = await execute(state)

    assert executed == [("kill_process", {"host": "lab-host", "pid": 344})]
    assert result["remediation"]["exit_status"] == 0
    assert "remediation executed" in [e.event for e in (await store.get(incident.id)).timeline]


async def test_state_reloaded_from_the_checkpointer_still_executes(incident, executed, make_event):
    """After the pause, LangGraph hands the node plain dicts rather than the models it stored."""
    state = state_for(incident, Decision(decision="approve", action_index=0))
    state["event"] = make_event()
    reloaded = {
        key: (value.model_dump(mode="json") if hasattr(value, "model_dump") else value) for key, value in state.items()
    }
    await execute(reloaded)

    assert executed == [("kill_process", {"host": "lab-host", "pid": 344})]


async def test_recovery_is_verified_after_the_remediation(incident, executed, make_event):
    state = state_for(incident, Decision(decision="approve", action_index=0))
    state["event"] = make_event()
    result = await execute(state)

    assert result["outcome"]["recovered"] is True
    record = await store.get(incident.id)
    assert record.status == "completed"
    assert [e.event for e in record.timeline][-3:] == ["remediation executed", "verifying recovery", "recovered"]


async def test_a_remediation_that_does_not_help_is_recorded_as_unresolved(incident, executed, monkeypatch, make_event):
    async def still_broken(host, **kwargs):
        return Outcome(recovered=False, cpu_percent=99.0, detail="cpu is still 99.0%")

    monkeypatch.setattr(approval_agent, "verify_recovery", still_broken)
    state = state_for(incident, Decision(decision="approve", action_index=0))
    state["event"] = make_event()
    await execute(state)

    record = await store.get(incident.id)
    assert record.status == "unresolved"
    assert "not resolved" in [e.event for e in record.timeline]


async def test_an_expired_approval_executes_nothing(incident, executed, make_event):
    state = state_for(incident, Decision(decision="approve", action_index=0))
    state["event"] = make_event()
    request = state["approval"]
    request.requested_at = datetime.now(UTC) - timedelta(minutes=31)
    request.expires_at = request.requested_at + timedelta(minutes=30)

    await execute(state)

    assert executed == []
    record = await store.get(incident.id)
    assert record.status == "expired"
    assert "approval expired" in [e.event for e in record.timeline]


async def test_rejection_executes_nothing(incident, executed, make_event):
    state = state_for(incident, Decision(decision="reject", note="load test is expected"))
    state["event"] = make_event()
    await execute(state)

    assert executed == []
    assert "remediation rejected" in [e.event for e in (await store.get(incident.id)).timeline]


async def test_a_non_executable_action_is_never_run(incident, executed, make_event):
    actions = [RemediationAction(action="manual", command="reboot", reason="turn it off and on")]
    state = state_for(incident, Decision(decision="approve", action_index=0), actions)
    state["event"] = make_event()
    await execute(state)

    assert executed == []
    assert "nothing executed" in [e.event for e in (await store.get(incident.id)).timeline]


async def test_a_policy_rejection_from_the_tool_is_recorded(incident, monkeypatch, make_event):
    async def refusing_tool(name, arguments):
        return {"host": "lab-host", "command": "kill -TERM 344", "rejected": "pid 344 is a system process"}

    monkeypatch.setattr(approval_agent, "call_tool", refusing_tool)
    state = state_for(incident, Decision(decision="approve", action_index=0))
    state["event"] = make_event()
    await execute(state)

    assert "remediation rejected by policy" in [e.event for e in (await store.get(incident.id)).timeline]
