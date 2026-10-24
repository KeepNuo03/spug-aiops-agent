import asyncio
import os
import sys
from datetime import UTC, datetime

import pytest
import pytest_asyncio

import db
from alerts import AlertEvent

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://aiops:aiops.local@localhost:5432/aiops")

if sys.platform == "win32":
    # psycopg's async mode cannot run on Windows' default proactor loop; the gateway itself only
    # ever runs on Linux, so this is a developer-machine concern only.
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


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


@pytest_asyncio.fixture
async def database():
    """A real Postgres, emptied between tests.

    Not a stand-in: the bugs a store layer has — json round-trips, type coercion, concurrent
    updates — are exactly the ones a fake would answer differently.
    """
    await db.connect(TEST_DATABASE_URL)
    try:
        async with (await db.pool()).connection() as conn:
            await conn.execute("TRUNCATE incidents")
        yield
    finally:
        await db.disconnect()
