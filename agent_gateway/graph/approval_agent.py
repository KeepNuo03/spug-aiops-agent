"""Approval and execution.

The graph stops at `interrupt()` while a human decides. The run is checkpointed to Redis, so the
pause outlives a gateway restart: resuming replays from the checkpoint instead of re-diagnosing.
"""

from langgraph.types import interrupt

from alerts import AlertEvent
from diagnosis.evidence import evidence_text
from diagnosis.models import VerifiedDiagnosis
from graph.state import AIOpsState, as_model
from incidents import store
from intent.classifier import Intent
from observability.structured_log import get_logger, log_event
from safety.hitl import ApprovalRequest, Decision, build_request
from tools_client import call_tool

log = get_logger("agent_gateway")


async def approval(state: AIOpsState) -> AIOpsState:
    incident_id = state.get("incident_id", "")
    if state.get("diagnosis") is None:
        store.update(incident_id, event="no remediation proposed", detail="nothing to approve")
        return {}

    diagnosis = as_model(state["diagnosis"], VerifiedDiagnosis)
    if not diagnosis.actions:
        store.update(incident_id, event="no remediation proposed", detail="nothing to approve")
        return {}

    request = build_request(
        incident_id=incident_id,
        host=as_model(state["intent"], Intent).entities.get("hostname", ""),
        root_cause=diagnosis.root_cause,
        actions=diagnosis.actions,
        evidence_blob=evidence_text(state.get("evidence", [])),
    )
    executable = [a for a in request.actions if a.executable]
    log_event(
        log,
        "approval_requested",
        fingerprint=as_model(state["event"], AlertEvent).fingerprint,
        executable=[a.command for a in executable],
        blocked=[a.blocked_reason for a in request.actions if a.blocked_reason],
    )
    store.update(
        incident_id,
        event="awaiting approval",
        detail=f"{len(executable)} of {len(request.actions)} proposed actions can be executed",
        status="awaiting_approval",
        approval=request.model_dump(mode="json"),
    )

    decision = Decision.model_validate(interrupt(request.model_dump(mode="json")))
    return {"decision": decision.model_dump(mode="json"), "approval": request.model_dump(mode="json")}


async def execute(state: AIOpsState) -> AIOpsState:
    incident_id = state.get("incident_id", "")
    if state.get("decision") is None or state.get("approval") is None:
        return {}

    decision = as_model(state["decision"], Decision)
    request = as_model(state["approval"], ApprovalRequest)
    fingerprint = as_model(state["event"], AlertEvent).fingerprint

    if decision.decision == "reject":
        log_event(log, "remediation_rejected", fingerprint=fingerprint, note=decision.note)
        store.update(incident_id, event="remediation rejected", detail=decision.note or "declined by operator")
        return {}

    chosen = next(
        (a for a in request.actions if a.executable and (decision.action_index in (None, a.index))),
        None,
    )
    if chosen is None:
        store.update(incident_id, event="nothing executed", detail="approved action is not executable")
        return {}

    store.update(incident_id, event="executing remediation", detail=chosen.command, status="executing")
    tool, arguments = (
        ("kill_process", {"host": request.host, "pid": chosen.action.pid})
        if chosen.action.action == "kill"
        else ("kill_by_name", {"host": request.host, "process_name": chosen.action.process_name})
    )
    try:
        result = await call_tool(tool, arguments)
    except Exception as exc:
        log_event(log, "remediation_failed", fingerprint=fingerprint, error=str(exc))
        store.update(incident_id, event="remediation failed", detail=str(exc), status="failed")
        return {}

    rejected = result.get("rejected")
    log_event(
        log,
        "remediation_executed",
        fingerprint=fingerprint,
        command=chosen.command,
        exit_status=result.get("exit_status"),
        rejected=rejected,
    )
    store.update(
        incident_id,
        event="remediation rejected by policy" if rejected else "remediation executed",
        detail=rejected or f"{chosen.command} (exit {result.get('exit_status')})",
    )
    return {"remediation": result}
