"""Postgres connection and schema.

Incidents are business records — they are queried, reported on, and the approval entries are an
audit trail — so they live in Postgres rather than in the Redis instance that holds graph
checkpoints. The columns the UI filters and sorts on are real columns; the nested parts of an
incident are JSONB, which keeps one table instead of five and still allows querying inside them.
"""

import os

from psycopg_pool import AsyncConnectionPool

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://aiops:aiops.local@localhost:5432/aiops")
RETENTION_DAYS = int(os.environ.get("INCIDENT_RETENTION_DAYS", 7))
RETENTION_COUNT = int(os.environ.get("INCIDENT_RETENTION_COUNT", 200))

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id          TEXT PRIMARY KEY,
    fingerprint TEXT        NOT NULL,
    alertname   TEXT        NOT NULL,
    hostname    TEXT,
    summary     TEXT        NOT NULL DEFAULT '',
    status      TEXT        NOT NULL,
    intent      TEXT,
    opened_at   TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL,
    timeline    JSONB       NOT NULL DEFAULT '[]'::jsonb,
    evidence    JSONB       NOT NULL DEFAULT '[]'::jsonb,
    diagnosis   JSONB,
    approval    JSONB
);
CREATE INDEX IF NOT EXISTS incidents_opened_at_idx ON incidents (opened_at DESC);
CREATE INDEX IF NOT EXISTS incidents_status_idx ON incidents (status);
"""

_pool: AsyncConnectionPool | None = None


async def pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("database pool is not open; call connect() during startup")
    return _pool


async def connect(dsn: str = DATABASE_URL) -> AsyncConnectionPool:
    """Open the pool and apply the schema. Failing here stops the gateway on purpose: falling back
    to memory would look like it worked while quietly losing the audit trail."""
    global _pool
    _pool = AsyncConnectionPool(dsn, min_size=1, max_size=10, open=False)
    await _pool.open(wait=True, timeout=30)
    async with _pool.connection() as conn:
        await conn.execute(SCHEMA)
    return _pool


async def disconnect() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def prune(days: int = RETENTION_DAYS, keep: int = RETENTION_COUNT) -> int:
    """Drop incidents past the retention window, and anything beyond the newest `keep`."""
    async with (await pool()).connection() as conn:
        result = await conn.execute(
            """
            DELETE FROM incidents
            WHERE opened_at < now() - make_interval(days => %s)
               OR id NOT IN (SELECT id FROM incidents ORDER BY opened_at DESC LIMIT %s)
            """,
            (days, keep),
        )
        return result.rowcount
