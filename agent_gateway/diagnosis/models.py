"""What the diagnosis step produces."""

from pydantic import BaseModel, Field


class CulpritProcess(BaseModel):
    name: str
    pid: int | None = None
    cpu_percent: float | None = None


class SuggestedCommand(BaseModel):
    command: str
    reason: str


class Diagnosis(BaseModel):
    """The model's answer. Nothing here is trusted until it has been cross-checked."""

    root_cause: str
    summary: str
    confidence: float = Field(ge=0, le=1)
    evidence_used: list[str] = Field(default_factory=list)
    culprit_process: CulpritProcess | None = None
    suggested_commands: list[SuggestedCommand] = Field(default_factory=list)


class VerifiedDiagnosis(Diagnosis):
    """A diagnosis after cross-checking, with the verdict attached."""

    verified: bool
    verification_note: str | None = None
    latency_ms: int | None = None
