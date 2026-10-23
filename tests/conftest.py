from datetime import UTC, datetime

import pytest

from alerts import AlertEvent


@pytest.fixture
def make_event():
    """Builds the alert our Prometheus rule produces; override any field per test."""

    def build(**overrides) -> AlertEvent:
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

    return build
