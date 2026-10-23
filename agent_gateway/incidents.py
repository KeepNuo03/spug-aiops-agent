"""In-memory record of what the agent did with each alert, plus change notifications for the UI.

Memory is enough while nothing depends on surviving a restart: the logs remain the durable record.
The approval step is what will need persistence, and that is when this moves to Redis.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from alerts import AlertEvent

Status = Literal["received", "classified", "collecting", "diagnosing", "completed", "skipped", "failed"]


def _now() -> datetime:
    return datetime.now(UTC)


class TimelineEntry(BaseModel):
    at: datetime = Field(default_factory=_now)
    event: str
    detail: str | None = None


class Incident(BaseModel):
    id: str
    fingerprint: str
    alertname: str
    hostname: str | None
    summary: str
    status: Status = "received"
    intent: str | None = None
    opened_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    diagnosis: dict[str, Any] | None = None


class IncidentStore:
    def __init__(self, capacity: int = 100) -> None:
        self._capacity = capacity
        self._incidents: dict[str, Incident] = {}
        self._subscribers: set[asyncio.Queue] = set()

    def open(self, event: AlertEvent) -> Incident:
        incident = Incident(
            id=f"{event.fingerprint}-{int(event.starts_at.timestamp())}",
            fingerprint=event.fingerprint,
            alertname=event.alertname,
            hostname=event.hostname,
            summary=event.summary,
            timeline=[TimelineEntry(event="alert received", detail=event.description)],
        )
        self._incidents[incident.id] = incident
        while len(self._incidents) > self._capacity:
            self._incidents.pop(next(iter(self._incidents)))
        self._publish(incident)
        return incident

    def update(self, incident_id: str, *, event: str, detail: str | None = None, **fields) -> None:
        incident = self._incidents.get(incident_id)
        if incident is None:
            return
        for name, value in fields.items():
            setattr(incident, name, value)
        incident.timeline.append(TimelineEntry(event=event, detail=detail))
        incident.updated_at = _now()
        self._publish(incident)

    def list(self) -> list[Incident]:
        return list(reversed(self._incidents.values()))

    def get(self, incident_id: str) -> Incident | None:
        return self._incidents.get(incident_id)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def _publish(self, incident: Incident) -> None:
        # A snapshot, not the live object: a subscriber reading later must see this transition,
        # not whatever the incident has become since.
        snapshot = incident.model_copy(deep=True)
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(snapshot)
            except asyncio.QueueFull:
                # A browser that cannot keep up gets the current state on its next reload.
                self._subscribers.discard(queue)


store = IncidentStore()
