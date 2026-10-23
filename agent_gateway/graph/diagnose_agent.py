"""Diagnose agent: ask the model for a root cause, then check its answer against the evidence."""

import time

from alerts import AlertEvent
from diagnosis.evidence import evidence_text, render_evidence
from diagnosis.llm import build_prompt, diagnose
from diagnosis.verify import verify
from graph.state import AIOpsState, as_model
from incidents import store
from observability.structured_log import get_logger, log_event

log = get_logger("agent_gateway")


async def diagnose_node(state: AIOpsState) -> AIOpsState:
    event = as_model(state["event"], AlertEvent)
    incident_id = state.get("incident_id", "")
    evidence = state.get("evidence", [])
    if not evidence:
        log_event(log, "diagnosis_skipped", fingerprint=event.fingerprint, reason="no_evidence")
        store.update(incident_id, event="diagnosis skipped", detail="no evidence collected", status="failed")
        return {}

    store.update(incident_id, event="diagnosing", detail="asking the model for a root cause", status="diagnosing")
    started = time.monotonic()
    try:
        answer = await diagnose(build_prompt(event, render_evidence(evidence)))
    except Exception as exc:
        log_event(log, "diagnosis_failed", fingerprint=event.fingerprint, error=str(exc))
        store.update(incident_id, event="diagnosis failed", detail=str(exc), status="failed")
        return {}

    report = verify(answer, evidence_text(evidence), [item["probe"] for item in evidence])
    report.latency_ms = int((time.monotonic() - started) * 1000)

    log_event(log, "diagnosis_completed", fingerprint=event.fingerprint, **report.model_dump(mode="json"))
    store.update(
        incident_id,
        event="diagnosis completed",
        detail=f"{report.root_cause} (confidence {report.confidence}, verified {report.verified})",
        diagnosis=report.model_dump(mode="json"),
    )
    return {"diagnosis": report.model_dump(mode="json")}
