import pytest

from graph import monitor_agent
from graph.monitor_agent import TOP_PROCESSES, TOP_SNAPSHOT, collect_evidence
from tools.command_policy import ensure_read_only


@pytest.fixture
def recorded_calls(monkeypatch):
    calls = []

    async def fake_call_tool(name, arguments):
        calls.append((name, arguments))
        return {"ok": True}

    monkeypatch.setattr(monitor_agent, "call_tool", fake_call_tool)
    return calls


async def test_collects_every_probe(recorded_calls):
    evidence = await collect_evidence("lab-host")
    assert [e["probe"] for e in evidence] == ["cpu_usage_trend", "load1", "top_processes", "top_snapshot"]
    assert all(e["result"] == {"ok": True} for e in evidence)


async def test_probes_target_the_alerting_host(recorded_calls):
    await collect_evidence("lab-host")
    metric_queries = [args["promql"] for name, args in recorded_calls if name == "query_metrics"]
    assert all('hostname="lab-host"' in query for query in metric_queries)
    assert all(args["host"] == "lab-host" for name, args in recorded_calls if name == "exec_command")


async def test_a_failing_probe_does_not_abort_the_rest(monkeypatch):
    async def flaky_call_tool(name, arguments):
        if name == "query_metrics":
            raise RuntimeError("prometheus unreachable")
        return {"ok": True}

    monkeypatch.setattr(monitor_agent, "call_tool", flaky_call_tool)
    evidence = await collect_evidence("lab-host")
    assert [e.get("error") is not None for e in evidence] == [True, True, False, False]


@pytest.mark.parametrize("command", [TOP_PROCESSES, TOP_SNAPSHOT])
def test_probe_commands_satisfy_the_read_only_policy(command):
    ensure_read_only(command)
