import time

import httpx
import pytest

from tools import prometheus_tools
from tools.prometheus_tools import query_instant, query_range


def fake_response(payload: dict):
    return httpx.Response(200, json=payload, request=httpx.Request("GET", "http://prometheus:9090"))


@pytest.fixture
def prometheus(monkeypatch):
    calls = {}

    def fake_get(url, params=None, timeout=None):
        calls["url"] = url
        calls["params"] = params
        return fake_response(calls["payload"])

    monkeypatch.setattr(prometheus_tools.httpx, "get", fake_get)
    return calls


def test_instant_query_returns_labels_and_values(prometheus):
    prometheus["payload"] = {
        "status": "success",
        "data": {"result": [{"metric": {"hostname": "lab-host"}, "value": [1758000000, "97.5"]}]},
    }
    assert query_instant("node_load1") == [{"labels": {"hostname": "lab-host"}, "value": 97.5}]
    assert prometheus["params"]["query"] == "node_load1"


def test_range_query_returns_samples(prometheus):
    prometheus["payload"] = {
        "status": "success",
        "data": {"result": [{"metric": {}, "values": [[1758000000, "1.0"], [1758000030, "2.0"]]}]},
    }
    [series] = query_range("node_load1", minutes=10)
    assert [s["value"] for s in series["samples"]] == [1.0, 2.0]
    # Prometheus rejects relative times such as "-10m": start/end must be absolute timestamps.
    params = prometheus["params"]
    assert params["end"] - params["start"] == 600
    assert params["end"] == pytest.approx(time.time(), abs=10)


def test_prometheus_error_is_raised(prometheus):
    prometheus["payload"] = {"status": "error", "error": "parse error"}
    with pytest.raises(RuntimeError, match="parse error"):
        query_instant("bad{")
