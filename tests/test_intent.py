import pytest

from intent.classifier import classify


def test_intent_label_wins(make_event):
    intent = classify(make_event())
    assert intent.name == "cpu_high"
    assert intent.matched_by == "label"
    assert intent.entities == {"hostname": "lab-host"}


def test_keyword_fallback_without_label(make_event):
    intent = classify(make_event(intent_hint=None))
    assert intent.name == "cpu_high"
    assert intent.matched_by == "keyword"


@pytest.mark.parametrize("field", ["alertname", "summary", "description"])
def test_keyword_matches_any_text_field(make_event, field):
    blank = {"alertname": "", "summary": "", "description": ""}
    intent = classify(make_event(intent_hint=None, **{**blank, field: "node load is too high"}))
    assert intent.name == "cpu_high"


def test_unknown_when_nothing_matches(make_event):
    intent = classify(
        make_event(intent_hint=None, alertname="DiskWillFillIn4Hours", summary="disk almost full", description="")
    )
    assert intent.name == "unknown"
    assert intent.confidence == 0.0
    assert intent.matched_by == "none"


def test_unsupported_label_falls_back_to_keywords(make_event):
    intent = classify(make_event(intent_hint="memory_leak"))
    assert intent.name == "cpu_high"
    assert intent.matched_by == "keyword"


def test_entities_empty_without_hostname(make_event):
    assert classify(make_event(hostname=None)).entities == {}
