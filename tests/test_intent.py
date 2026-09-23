from datetime import UTC, datetime

import pytest

from alerts import AlertEvent
from intent.classifier import classify


def make_event(**overrides) -> AlertEvent:
    defaults = dict(
        source="alertmanager",
        fingerprint="abc123",
        status="firing",
        alertname="HostHighCpuUsage",
        hostname="lab-host",
        severity="warning",
        intent_hint="cpu_high",
        summary="High CPU usage on lab-host",
        description="CPU usage is 100.0% (> 80%) for more than 1 minute.",
        starts_at=datetime(2026, 9, 23, 8, 0, tzinfo=UTC),
        labels={},
    )
    return AlertEvent(**{**defaults, **overrides})


def test_intent_label_wins():
    intent = classify(make_event())
    assert intent.name == "cpu_high"
    assert intent.matched_by == "label"
    assert intent.entities == {"hostname": "lab-host"}


def test_keyword_fallback_without_label():
    intent = classify(make_event(intent_hint=None))
    assert intent.name == "cpu_high"
    assert intent.matched_by == "keyword"


@pytest.mark.parametrize("field", ["alertname", "summary", "description"])
def test_keyword_matches_any_text_field(field):
    blank = {"alertname": "", "summary": "", "description": ""}
    intent = classify(make_event(intent_hint=None, **{**blank, field: "node load is too high"}))
    assert intent.name == "cpu_high"


def test_unknown_when_nothing_matches():
    intent = classify(
        make_event(intent_hint=None, alertname="DiskWillFillIn4Hours", summary="disk almost full", description="")
    )
    assert intent.name == "unknown"
    assert intent.confidence == 0.0
    assert intent.matched_by == "none"


def test_unsupported_label_falls_back_to_keywords():
    intent = classify(make_event(intent_hint="memory_leak"))
    assert intent.name == "cpu_high"
    assert intent.matched_by == "keyword"


def test_entities_empty_without_hostname():
    assert classify(make_event(hostname=None)).entities == {}
