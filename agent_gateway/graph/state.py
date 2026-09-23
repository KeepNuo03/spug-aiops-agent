"""AIOpsState: what flows between the agents handling one alert."""

from typing import Any, TypedDict

from alerts import AlertEvent
from intent.classifier import Intent


class AIOpsState(TypedDict, total=False):
    event: AlertEvent
    intent: Intent
    evidence: list[dict[str, Any]]
