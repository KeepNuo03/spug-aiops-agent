"""Rule-based intent classification.

Alerts from our own Prometheus rules carry an `intent` label, which is authoritative. Alerts from
elsewhere are matched on keywords. Anything else is `unknown` and is not processed further; an LLM
classifier layer comes later, when free-form chat input needs to be handled.
"""

from typing import Literal

from pydantic import BaseModel

from alerts import AlertEvent

IntentName = Literal["cpu_high", "unknown"]

INTENT_KEYWORDS: dict[IntentName, tuple[str, ...]] = {
    "cpu_high": ("cpu", "load", "processor"),
}


class Intent(BaseModel):
    name: IntentName
    confidence: float
    matched_by: Literal["label", "keyword", "none"]
    entities: dict[str, str]


def classify(event: AlertEvent) -> Intent:
    entities = {"hostname": event.hostname} if event.hostname else {}

    if event.intent_hint in INTENT_KEYWORDS:
        return Intent(name=event.intent_hint, confidence=0.95, matched_by="label", entities=entities)

    haystack = " ".join([event.alertname, event.summary, event.description]).lower()
    for name, keywords in INTENT_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            return Intent(name=name, confidence=0.7, matched_by="keyword", entities=entities)

    return Intent(name="unknown", confidence=0.0, matched_by="none", entities=entities)
