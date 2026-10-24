import asyncio
from datetime import UTC, datetime, timedelta

import pytest

import db
from incidents import IncidentStore, store

pytestmark = pytest.mark.usefixtures("database")


@pytest.fixture
def fresh_store():
    return IncidentStore()


async def test_opening_an_incident_records_the_alert(fresh_store, make_event):
    incident = await fresh_store.open(make_event())
    assert incident.alertname == "HostHighCpuUsage"
    assert incident.hostname == "lab-host"
    assert incident.status == "received"
    assert [e.event for e in incident.timeline] == ["alert received"]


async def test_an_incident_survives_a_new_store(fresh_store, make_event):
    """A restart loses the object, not the record: that is the point of persisting it."""
    incident = await fresh_store.open(make_event())
    await fresh_store.update(incident.id, event="intent classified", status="classified", intent="cpu_high")

    reloaded = await IncidentStore().get(incident.id)
    assert reloaded.status == "classified"
    assert reloaded.intent == "cpu_high"
    assert [e.event for e in reloaded.timeline] == ["alert received", "intent classified"]


async def test_same_alert_firing_again_is_a_separate_incident(fresh_store, make_event):
    first = await fresh_store.open(make_event())
    second = await fresh_store.open(make_event(starts_at=datetime(2026, 9, 23, 9, 0, tzinfo=UTC)))
    assert first.id != second.id
    assert len(await fresh_store.list()) == 2


async def test_reopening_the_same_incident_keeps_the_first_record(fresh_store, make_event):
    incident = await fresh_store.open(make_event())
    await fresh_store.update(incident.id, event="diagnosing", status="diagnosing")
    await fresh_store.open(make_event())

    reloaded = await fresh_store.get(incident.id)
    assert reloaded.status == "diagnosing"
    assert len(reloaded.timeline) == 2


async def test_nested_structures_round_trip(fresh_store, make_event):
    incident = await fresh_store.open(make_event())
    evidence = [{"probe": "top_processes", "tool": "exec_command", "result": {"output": "344 stress-ng"}}]
    diagnosis = {"root_cause": "stress-ng", "confidence": 0.95, "culprit_process": {"name": "stress-ng", "pid": 344}}
    await fresh_store.update(incident.id, event="diagnosis completed", evidence=evidence, diagnosis=diagnosis)

    reloaded = await fresh_store.get(incident.id)
    assert reloaded.evidence == evidence
    assert reloaded.diagnosis["culprit_process"]["pid"] == 344


async def test_updating_an_unknown_incident_is_ignored(fresh_store):
    await fresh_store.update("nope", event="whatever")


async def test_list_is_newest_first(fresh_store, make_event):
    older = await fresh_store.open(make_event(fingerprint="old"))
    newer = await fresh_store.open(make_event(fingerprint="new", starts_at=datetime(2026, 9, 24, 8, 0, tzinfo=UTC)))
    # Set the open times apart explicitly: both rows are written within one clock tick, and on a
    # coarse clock they would otherwise carry the same timestamp.
    async with (await db.pool()).connection() as conn:
        await conn.execute(
            "UPDATE incidents SET opened_at = %s WHERE id = %s",
            (datetime.now(UTC) - timedelta(hours=1), older.id),
        )

    assert [i.id for i in await fresh_store.list()] == [newer.id, older.id]


async def test_subscribers_receive_each_change(fresh_store, make_event):
    queue = fresh_store.subscribe()
    incident = await fresh_store.open(make_event())
    await fresh_store.update(incident.id, event="diagnosing", status="diagnosing")

    first = await asyncio.wait_for(queue.get(), timeout=1)
    second = await asyncio.wait_for(queue.get(), timeout=1)
    assert [first.status, second.status] == ["received", "diagnosing"]


async def test_unsubscribed_queues_stop_receiving(fresh_store, make_event):
    queue = fresh_store.subscribe()
    fresh_store.unsubscribe(queue)
    await fresh_store.open(make_event())
    assert queue.empty()


async def test_a_stalled_subscriber_is_dropped(fresh_store, make_event):
    queue = fresh_store.subscribe()
    for i in range(queue.maxsize + 5):
        await fresh_store.open(make_event(fingerprint=f"fp{i}"))
    # The queue filled up and the subscriber was discarded rather than blocking the handler.
    assert queue.qsize() == queue.maxsize


async def test_retention_drops_old_incidents(fresh_store, make_event):
    recent = await fresh_store.open(make_event(fingerprint="recent"))
    stale = await fresh_store.open(make_event(fingerprint="stale"))
    async with (await db.pool()).connection() as conn:
        await conn.execute(
            "UPDATE incidents SET opened_at = %s WHERE id = %s",
            (datetime.now(UTC) - timedelta(days=30), stale.id),
        )

    assert await db.prune(days=7, keep=100) == 1
    assert [i.id for i in await fresh_store.list()] == [recent.id]


async def test_retention_keeps_only_the_newest_when_over_count(fresh_store, make_event):
    for i in range(5):
        await fresh_store.open(make_event(fingerprint=f"fp{i}", starts_at=datetime(2026, 9, 23, 8, i, tzinfo=UTC)))

    assert await db.prune(days=7, keep=3) == 2
    assert len(await fresh_store.list()) == 3


async def test_module_store_uses_the_same_table(make_event):
    incident = await store.open(make_event())
    assert await IncidentStore().get(incident.id) is not None
