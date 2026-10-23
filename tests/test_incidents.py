import asyncio

import pytest

from incidents import IncidentStore


@pytest.fixture
def store():
    return IncidentStore(capacity=3)


def test_opening_an_incident_records_the_alert(store, make_event):
    incident = store.open(make_event())
    assert incident.alertname == "HostHighCpuUsage"
    assert incident.hostname == "lab-host"
    assert incident.status == "received"
    assert [e.event for e in incident.timeline] == ["alert received"]


def test_same_alert_firing_again_is_a_separate_incident(store, make_event):
    from datetime import UTC, datetime

    first = store.open(make_event())
    second = store.open(make_event(starts_at=datetime(2026, 9, 23, 9, 0, tzinfo=UTC)))
    assert first.id != second.id
    assert len(store.list()) == 2


def test_updates_append_to_the_timeline(store, make_event):
    incident = store.open(make_event())
    store.update(incident.id, event="intent classified", detail="cpu_high", status="classified", intent="cpu_high")
    updated = store.get(incident.id)
    assert updated.status == "classified"
    assert updated.intent == "cpu_high"
    assert [e.event for e in updated.timeline] == ["alert received", "intent classified"]


def test_updating_an_unknown_incident_is_ignored(store):
    store.update("nope", event="whatever")


def test_oldest_incidents_are_dropped_at_capacity(store, make_event):
    for i in range(5):
        store.open(make_event(fingerprint=f"fp{i}"))
    assert len(store.list()) == 3


def test_list_is_newest_first(store, make_event):
    older = store.open(make_event(fingerprint="old"))
    newer = store.open(make_event(fingerprint="new"))
    assert [i.id for i in store.list()] == [newer.id, older.id]


async def test_subscribers_receive_changes(store, make_event):
    queue = store.subscribe()
    incident = store.open(make_event())
    store.update(incident.id, event="diagnosing", status="diagnosing")

    first = await asyncio.wait_for(queue.get(), timeout=1)
    second = await asyncio.wait_for(queue.get(), timeout=1)
    assert first.status == "received"
    assert second.status == "diagnosing"


async def test_unsubscribed_queues_stop_receiving(store, make_event):
    queue = store.subscribe()
    store.unsubscribe(queue)
    store.open(make_event())
    assert queue.empty()


def test_a_stalled_subscriber_is_dropped(make_event):
    store = IncidentStore()
    queue = store.subscribe()
    for i in range(queue.maxsize + 5):
        store.open(make_event(fingerprint=f"fp{i}"))
    # The queue filled up and the subscriber was discarded rather than blocking the handler.
    assert queue.qsize() == queue.maxsize
