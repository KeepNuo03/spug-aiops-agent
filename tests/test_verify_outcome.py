from datetime import UTC, datetime, timedelta

import pytest

from diagnosis import verify_outcome
from diagnosis.models import RemediationAction
from diagnosis.verify_outcome import verify_recovery
from safety.hitl import build_request


@pytest.fixture
def metrics(monkeypatch):
    state = {}

    async def fake_call_tool(name, arguments):
        state["query"] = arguments["promql"]
        if isinstance(state["reply"], Exception):
            raise state["reply"]
        return state["reply"]

    monkeypatch.setattr(verify_outcome, "call_tool", fake_call_tool)
    return state


def series(value):
    return {"series": [{"labels": {"hostname": "lab-host"}, "value": value}]}


async def test_cpu_back_under_the_threshold_is_recovery(metrics):
    metrics["reply"] = series(0.2)
    outcome = await verify_recovery("lab-host", settle_seconds=0)
    assert outcome.recovered
    assert outcome.cpu_percent == 0.2
    assert "back under" in outcome.detail


async def test_cpu_still_high_is_not_resolved(metrics):
    metrics["reply"] = series(99.0)
    outcome = await verify_recovery("lab-host", settle_seconds=0)
    assert not outcome.recovered
    assert "did not resolve" in outcome.detail


async def test_verification_targets_the_alerting_host(metrics):
    metrics["reply"] = series(1.0)
    await verify_recovery("lab-host", settle_seconds=0)
    assert 'hostname="lab-host"' in metrics["query"]


async def test_a_failed_query_is_not_reported_as_recovery(metrics):
    metrics["reply"] = RuntimeError("prometheus unreachable")
    outcome = await verify_recovery("lab-host", settle_seconds=0)
    assert not outcome.recovered
    assert "could not verify" in outcome.detail


async def test_missing_samples_are_not_reported_as_recovery(metrics):
    metrics["reply"] = {"series": []}
    outcome = await verify_recovery("lab-host", settle_seconds=0)
    assert not outcome.recovered
    assert outcome.cpu_percent is None


def request_at(when):
    request = build_request(
        "incident-1",
        "lab-host",
        "cause",
        [RemediationAction(action="kill", pid=344, reason="stop it")],
        "344 stress-ng",
    )
    request.requested_at = when
    request.expires_at = when + timedelta(minutes=30)
    return request


def test_a_fresh_approval_is_not_expired():
    assert not request_at(datetime.now(UTC)).is_expired()


def test_an_approval_older_than_the_window_is_expired():
    assert request_at(datetime.now(UTC) - timedelta(minutes=31)).is_expired()


def test_expiry_is_evaluated_at_the_boundary():
    requested = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    request = request_at(requested)
    assert not request.is_expired(requested + timedelta(minutes=29, seconds=59))
    assert request.is_expired(requested + timedelta(minutes=30))
