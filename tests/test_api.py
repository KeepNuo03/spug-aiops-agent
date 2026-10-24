import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from incidents import store
from main import app, incident_events

client = TestClient(app)


pytestmark = pytest.mark.usefixtures("database")


def test_incident_list_starts_empty():
    assert client.get("/api/incidents").json() == []


async def test_incident_appears_in_the_list(make_event):
    incident = await store.open(make_event())
    [listed] = client.get("/api/incidents").json()
    assert listed["id"] == incident.id
    assert listed["alertname"] == "HostHighCpuUsage"


async def test_incident_detail_includes_timeline_and_diagnosis(make_event):
    incident = await store.open(make_event())
    await store.update(
        incident.id, event="diagnosis completed", status="completed", diagnosis={"root_cause": "stress-ng"}
    )

    detail = client.get(f"/api/incidents/{incident.id}").json()
    assert detail["status"] == "completed"
    assert detail["diagnosis"]["root_cause"] == "stress-ng"
    assert [e["event"] for e in detail["timeline"]] == ["alert received", "diagnosis completed"]


def test_unknown_incident_is_404():
    assert client.get("/api/incidents/nope").status_code == 404


async def test_stream_sends_each_change_as_an_event(make_event):
    events = incident_events()
    pending = asyncio.ensure_future(anext(events))
    await asyncio.sleep(0)  # let the generator subscribe before anything is published

    incident = await store.open(make_event())
    await store.update(incident.id, event="diagnosing", status="diagnosing")

    first = await asyncio.wait_for(pending, timeout=1)
    second = await asyncio.wait_for(anext(events), timeout=1)
    await events.aclose()

    assert first.startswith("data: ") and first.endswith("\n\n")
    assert [json.loads(message[6:])["status"] for message in (first, second)] == ["received", "diagnosing"]


def test_ui_is_served():
    page = client.get("/")
    assert page.status_code == 200
    assert "Spug AIOps Agent" in page.text
    assert client.get("/static/app.js").status_code == 200
