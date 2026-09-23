import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import processing
from alerts import AlertmanagerPayload, to_events
from main import app
from processing import _dedup

FIXTURE = Path(__file__).parent / "fixtures" / "alertmanager_cpu_high_firing.json"
client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_dedup():
    _dedup.clear()


@pytest.fixture(autouse=True)
def stub_graph(monkeypatch):
    """Background handling runs inside the test client; keep it away from the real MCP server."""
    handled = []

    async def fake_run(event, intent):
        handled.append((event, intent))
        return {"evidence": []}

    monkeypatch.setattr(processing, "run", fake_run)
    return handled


@pytest.fixture
def payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_firing_alert_is_accepted(payload):
    resp = client.post("/webhook/alertmanager", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"received": 1, "accepted": 1}


def test_resolved_alert_is_not_handled(payload):
    payload["status"] = "resolved"
    payload["alerts"][0]["status"] = "resolved"
    resp = client.post("/webhook/alertmanager", json=payload)
    assert resp.json() == {"received": 1, "accepted": 0}


def test_repeated_alert_is_handled_once(payload):
    assert client.post("/webhook/alertmanager", json=payload).json()["accepted"] == 1
    assert client.post("/webhook/alertmanager", json=payload).json()["accepted"] == 0


def test_alert_firing_again_is_a_new_incident(payload):
    client.post("/webhook/alertmanager", json=payload)
    payload["alerts"][0]["startsAt"] = "2026-09-23T09:30:00.000Z"
    assert client.post("/webhook/alertmanager", json=payload).json()["accepted"] == 1


def test_invalid_payload_is_rejected():
    resp = client.post("/webhook/alertmanager", json={"foo": "bar"})
    assert resp.status_code == 422


def test_to_events_extracts_host_and_intent(payload):
    [event] = to_events(AlertmanagerPayload.model_validate(payload))
    assert event.alertname == "HostHighCpuUsage"
    assert event.hostname == "lab-host"
    assert event.intent_hint == "cpu_high"
    assert event.severity == "warning"
    assert event.summary == "High CPU usage on lab-host"


def test_to_events_tolerates_missing_optional_labels(payload):
    labels = payload["alerts"][0]["labels"]
    del labels["hostname"], labels["intent"]
    [event] = to_events(AlertmanagerPayload.model_validate(payload))
    assert event.hostname is None
    assert event.intent_hint is None


def test_healthz():
    assert client.get("/healthz").json() == {"status": "ok"}
