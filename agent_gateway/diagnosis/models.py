"""What the diagnosis step produces."""

from typing import Literal

from pydantic import BaseModel, Field


class CulpritProcess(BaseModel):
    name: str
    pid: int | None = None
    cpu_percent: float | None = None


class RemediationAction(BaseModel):
    """What the model proposes doing about the incident.

    The executable actions are structured on purpose: the model names a pid or a process name, and
    the command is rendered from it, so a model reply never becomes a shell string. Anything else
    is `manual` — shown to the engineer with the command the model suggests, never run by the agent.
    """

    action: Literal["kill", "kill_by_name", "manual"]
    reason: str
    pid: int | None = None
    process_name: str | None = None
    command: str | None = None


class Diagnosis(BaseModel):
    """The model's answer. Nothing here is trusted until it has been cross-checked."""

    root_cause: str
    summary: str
    confidence: float = Field(ge=0, le=1)
    evidence_used: list[str] = Field(default_factory=list)
    culprit_process: CulpritProcess | None = None
    actions: list[RemediationAction] = Field(default_factory=list)


class VerifiedDiagnosis(Diagnosis):
    """A diagnosis after cross-checking, with the verdict attached."""

    verified: bool
    verification_note: str | None = None
    latency_ms: int | None = None
