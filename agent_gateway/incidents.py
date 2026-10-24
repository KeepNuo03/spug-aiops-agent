"""The record of what the agent did with each alert.

Stored in Postgres: an incident carries the approval audit trail, and a record of who allowed a
command to run on a host has to survive a restart. The subscriber set stays in memory — it is this
process's open browser connections, not state worth persisting.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any, Literal

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from alerts import AlertEvent
from db import pool

Status = Literal[
    "received",
    "classified",
    "collecting",
    "diagnosing",
    "awaiting_approval",
    "executing",
    "completed",
    "unresolved",
    "expired",
    "skipped",
    "failed",
]

COLUMNS = (
    "id, fingerprint, alertname, hostname, summary, status, intent, "
    "opened_at, updated_at, timeline, evidence, diagnosis, approval"
)
JSON_FIELDS = ("evidence", "diagnosis", "approval")
WRITABLE_FIELDS = ("status", "intent", "evidence", "diagnosis", "approval")


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
    approval: dict[str, Any] | None = None


class IncidentStore:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    async def open(self, event: AlertEvent) -> Incident:
        incident = Incident(
            id=f"{event.fingerprint}-{int(event.starts_at.timestamp())}",
            fingerprint=event.fingerprint,
            alertname=event.alertname,
            hostname=event.hostname,
            summary=event.summary,
            timeline=[TimelineEntry(event="alert received", detail=event.description)],
        )
        async with (await pool()).connection() as conn:
            await conn.execute(
                """
                INSERT INTO incidents (id, fingerprint, alertname, hostname, summary, status,
                                       opened_at, updated_at, timeline)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    incident.id,
                    incident.fingerprint,
                    incident.alertname,
                    incident.hostname,
                    incident.summary,
                    incident.status,
                    incident.opened_at,
                    incident.updated_at,
                    Jsonb([entry.model_dump(mode="json") for entry in incident.timeline]),
                ),
            )
        self._publish(incident)
        return incident

    async def update(self, incident_id: str, *, event: str, detail: str | None = None, **fields) -> None:
        """Append a timeline entry and set any of the writable columns, in one statement."""
        entry = TimelineEntry(event=event, detail=detail)
        updates = {name: value for name, value in fields.items() if name in WRITABLE_FIELDS}
        assignments = "".join(f", {name} = %s" for name in updates)

        async with (await pool()).connection() as conn:
            conn.row_factory = dict_row
            cursor = await conn.execute(
                f"""
                   UPDATE incidents
                      SET timeline = timeline || %s, updated_at = %s{assignments}
                    WHERE id = %s
                RETURNING {COLUMNS}
                """,
                (
                    Jsonb([entry.model_dump(mode="json")]),
                    _now(),
                    *(Jsonb(value) if name in JSON_FIELDS else value for name, value in updates.items()),
                    incident_id,
                ),
            )
            row = await cursor.fetchone()

        if row is not None:
            self._publish(Incident.model_validate(row))

    async def list(self, limit: int = 100) -> list[Incident]:
        async with (await pool()).connection() as conn:
            conn.row_factory = dict_row
            # id breaks ties: two alerts can open within the same clock tick, and a list whose order
            # depends on which row the planner reached first is not a list.
            cursor = await conn.execute(
                f"SELECT {COLUMNS} FROM incidents ORDER BY opened_at DESC, id DESC LIMIT %s", (limit,)
            )
            return [Incident.model_validate(row) for row in await cursor.fetchall()]

    async def get(self, incident_id: str) -> Incident | None:
        async with (await pool()).connection() as conn:
            conn.row_factory = dict_row
            cursor = await conn.execute(f"SELECT {COLUMNS} FROM incidents WHERE id = %s", (incident_id,))
            row = await cursor.fetchone()
            return Incident.model_validate(row) if row else None

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def _publish(self, incident: Incident) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(incident)
            except asyncio.QueueFull:
                # A browser that cannot keep up gets the current state on its next reload.
                self._subscribers.discard(queue)


store = IncidentStore()
