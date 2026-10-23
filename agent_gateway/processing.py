"""Alert intake and handling.

Alertmanager re-sends a firing alert every `repeat_interval`, so the same incident must not be
handled twice; an alert that fires again after recovering has a new `starts_at` and is a new
incident. Handling runs in the background because the webhook has to answer before Alertmanager
times out.
"""

from collections import OrderedDict

from alerts import AlertEvent
from graph.supervisor import is_awaiting_approval, resume, run
from incidents import store
from intent.classifier import classify
from observability.structured_log import get_logger, log_event
from safety.hitl import Decision

log = get_logger("agent_gateway")


class Deduplicator:
    def __init__(self, capacity: int = 1000) -> None:
        self._capacity = capacity
        self._seen: OrderedDict[str, str] = OrderedDict()

    def is_duplicate(self, event: AlertEvent) -> bool:
        starts_at = event.starts_at.isoformat()
        if self._seen.get(event.fingerprint) == starts_at:
            return True
        self._seen[event.fingerprint] = starts_at
        self._seen.move_to_end(event.fingerprint)
        while len(self._seen) > self._capacity:
            self._seen.popitem(last=False)
        return False

    def clear(self) -> None:
        self._seen.clear()


_dedup = Deduplicator()


def skip_reason(event: AlertEvent) -> str | None:
    """Why this event should not be handled, or None. Records firing events for deduplication."""
    if event.status != "firing":
        return "not_firing"
    if _dedup.is_duplicate(event):
        return "duplicate"
    return None


async def handle_alert(event: AlertEvent) -> None:
    incident = store.open(event)
    intent = classify(event)
    log_event(
        log,
        "intent_classified",
        fingerprint=event.fingerprint,
        alertname=event.alertname,
        intent=intent.name,
        confidence=intent.confidence,
        matched_by=intent.matched_by,
        entities=intent.entities,
    )
    store.update(
        incident.id,
        event="intent classified",
        detail=f"{intent.name} (confidence {intent.confidence}, by {intent.matched_by})",
        status="classified",
        intent=intent.name,
    )

    if intent.name == "unknown":
        log_event(log, "handling_skipped", fingerprint=event.fingerprint, reason="unknown_intent")
        store.update(incident.id, event="handling skipped", detail="intent not recognized", status="skipped")
        return

    try:
        state = await run(event, intent, incident.id)
    except Exception as exc:
        # Nothing is watching a background task, so a crash has to land on the incident itself.
        log_event(log, "handling_crashed", fingerprint=event.fingerprint, error=str(exc))
        store.update(incident.id, event="handling crashed", detail=str(exc), status="failed")
        raise

    _finish(incident.id, event.fingerprint, intent.name, state)


def _finish(incident_id: str, fingerprint: str, intent_name: str, state: dict) -> None:
    if is_awaiting_approval(state):
        return  # the run is paused; apply_decision resumes it

    log_event(
        log,
        "handling_finished",
        fingerprint=fingerprint,
        intent=intent_name,
        evidence_probes=len(state.get("evidence", [])),
    )
    current = store.get(incident_id)
    if current and current.status != "failed":
        store.update(incident_id, event="handling finished", status="completed")


async def apply_decision(incident_id: str, decision: Decision) -> None:
    """Resume a paused run once a human has decided."""
    incident = store.get(incident_id)
    if incident is None:
        raise LookupError("no such incident")
    if incident.status != "awaiting_approval":
        raise ValueError(f"incident is {incident.status}, not awaiting approval")

    store.update(incident_id, event=f"operator {decision.decision}d", detail=decision.note)
    state = await resume(incident_id, decision)
    _finish(incident_id, incident.fingerprint, incident.intent or "", state)
