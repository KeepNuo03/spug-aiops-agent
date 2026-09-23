"""Alert intake and handling.

Alertmanager re-sends a firing alert every `repeat_interval`, so the same incident must not be
handled twice; an alert that fires again after recovering has a new `starts_at` and is a new
incident. Handling runs in the background because the webhook has to answer before Alertmanager
times out.
"""

from collections import OrderedDict

from alerts import AlertEvent
from intent.classifier import classify
from observability.structured_log import get_logger, log_event

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


def handle_alert(event: AlertEvent) -> None:
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
    if intent.name == "unknown":
        log_event(log, "handling_skipped", fingerprint=event.fingerprint, reason="unknown_intent")
        return
