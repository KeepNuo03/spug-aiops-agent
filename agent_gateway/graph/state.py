"""AIOpsState: what flows between the agents handling one alert.

The state holds plain JSON-able dicts rather than models. Checkpointing serializes whatever the
state contains, and models come back wrapped in the serializer's own envelope; keeping dicts in
the state means a node sees the same shape whether the run is fresh or resumed from Redis.
"""

from typing import Any, TypedDict


def as_model(value, model):
    """Restore a model from the dict kept in state."""
    return value if isinstance(value, model) else model.model_validate(value)


class AIOpsState(TypedDict, total=False):
    event: dict[str, Any]
    intent: dict[str, Any]
    incident_id: str
    evidence: list[dict[str, Any]]
    diagnosis: dict[str, Any]
    approval: dict[str, Any]
    decision: dict[str, Any]
    remediation: dict[str, Any]
