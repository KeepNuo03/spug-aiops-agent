"""Prometheus queries: instant values and short range windows, reduced to compact JSON."""

import os
import time

import httpx

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")


def _get(path: str, params: dict) -> dict:
    resp = httpx.get(f"{PROMETHEUS_URL}/api/v1{path}", params=params, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    if body.get("status") != "success":
        raise RuntimeError(f"prometheus error: {body.get('error', 'unknown')}")
    return body["data"]


def query_instant(promql: str) -> list[dict]:
    """Current value of each series matching the query."""
    data = _get("/query", {"query": promql})
    return [{"labels": r["metric"], "value": float(r["value"][1])} for r in data["result"]]


def query_range(promql: str, minutes: int = 10, step: str = "30s") -> list[dict]:
    """Samples over the last `minutes`, one series per entry."""
    end = time.time()
    data = _get("/query_range", {"query": promql, "start": end - minutes * 60, "end": end, "step": step})
    return [
        {
            "labels": r["metric"],
            "samples": [{"ts": float(ts), "value": float(value)} for ts, value in r["values"]],
        }
        for r in data["result"]
    ]
