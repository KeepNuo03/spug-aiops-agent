"""Alert models: the Alertmanager webhook payload (v4) and the source-agnostic AlertEvent used downstream."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AlertStatus = Literal["firing", "resolved"]


class Alert(BaseModel):
    status: AlertStatus
    labels: dict[str, str]
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: datetime
    fingerprint: str


class AlertmanagerPayload(BaseModel):
    version: str
    status: AlertStatus
    receiver: str
    groupKey: str
    alerts: list[Alert]


class AlertEvent(BaseModel):
    source: Literal["alertmanager"]
    fingerprint: str
    status: AlertStatus
    alertname: str
    hostname: str | None
    severity: str | None
    intent_hint: str | None
    summary: str
    description: str
    starts_at: datetime
    labels: dict[str, str]


def to_events(payload: AlertmanagerPayload) -> list[AlertEvent]:
    return [
        AlertEvent(
            source="alertmanager",
            fingerprint=alert.fingerprint,
            status=alert.status,
            alertname=alert.labels.get("alertname", ""),
            hostname=alert.labels.get("hostname"),
            severity=alert.labels.get("severity"),
            intent_hint=alert.labels.get("intent"),
            summary=alert.annotations.get("summary", ""),
            description=alert.annotations.get("description", ""),
            starts_at=alert.startsAt,
            labels=alert.labels,
        )
        for alert in payload.alerts
    ]
