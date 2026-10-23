"""The approval request a human acts on, and the decision that comes back."""

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from diagnosis.models import RemediationAction
from safety.risk import Risk, classify, render_command

APPROVAL_TTL = timedelta(minutes=30)


class ProposedAction(BaseModel):
    """One action as offered to the engineer, with the verdict on whether the agent may run it."""

    index: int
    action: RemediationAction
    risk: Risk
    executable: bool
    command: str | None = None
    blocked_reason: str | None = None


class ApprovalRequest(BaseModel):
    incident_id: str
    host: str
    root_cause: str
    actions: list[ProposedAction]
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(default_factory=lambda: datetime.now(UTC) + APPROVAL_TTL)


class Decision(BaseModel):
    decision: Literal["approve", "reject"]
    action_index: int | None = None
    note: str | None = None


def build_request(incident_id: str, host: str, root_cause: str, actions, evidence_blob: str) -> ApprovalRequest:
    proposed = []
    for index, action in enumerate(actions):
        risk, blocked = classify(action, evidence_blob)
        executable = risk == "dangerous" and blocked is None
        proposed.append(
            ProposedAction(
                index=index,
                action=action,
                risk=risk,
                executable=executable,
                command=render_command(action) if executable else action.command,
                blocked_reason=blocked,
            )
        )
    return ApprovalRequest(incident_id=incident_id, host=host, root_cause=root_cause, actions=proposed)
