"""Monitor agent: collects the evidence a CPU diagnosis needs.

The probes are fixed for now — an LLM picking its own queries comes later. Each probe is recorded
with its result (or its error) so a failing probe degrades the evidence instead of the whole run.
"""

from typing import Any

from alerts import AlertEvent
from graph.state import AIOpsState, as_model
from incidents import store
from intent.classifier import Intent
from observability.structured_log import get_logger, log_event
from tools_client import call_tool

log = get_logger("agent_gateway")

CPU_USAGE = '100 - (avg by (hostname) (rate(node_cpu_seconds_total{{mode="idle", hostname="{host}"}}[1m])) * 100)'
LOAD1 = 'node_load1{{hostname="{host}"}}'
TOP_PROCESSES = "ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -11"
TOP_SNAPSHOT = "top -bn1 | head -15"


async def collect_evidence(host: str) -> list[dict[str, Any]]:
    probes = [
        ("cpu_usage_trend", "query_metrics", {"promql": CPU_USAGE.format(host=host), "range_minutes": 10}),
        ("load1", "query_metrics", {"promql": LOAD1.format(host=host)}),
        ("top_processes", "exec_command", {"host": host, "command": TOP_PROCESSES}),
        ("top_snapshot", "exec_command", {"host": host, "command": TOP_SNAPSHOT}),
    ]

    evidence = []
    for name, tool, arguments in probes:
        try:
            evidence.append({"probe": name, "tool": tool, "result": await call_tool(tool, arguments)})
        except Exception as exc:
            log_event(log, "probe_failed", probe=name, tool=tool, error=str(exc))
            evidence.append({"probe": name, "tool": tool, "error": str(exc)})
    return evidence


async def monitor(state: AIOpsState) -> AIOpsState:
    event = as_model(state["event"], AlertEvent)
    host = as_model(state["intent"], Intent).entities.get("hostname")
    if not host:
        log_event(log, "monitor_skipped", reason="no_hostname", fingerprint=event.fingerprint)
        return {"evidence": []}

    incident_id = state.get("incident_id", "")
    await store.update(incident_id, event="collecting evidence", detail=f"probing {host}", status="collecting")

    evidence = await collect_evidence(host)
    failed = [e["probe"] for e in evidence if "error" in e]
    log_event(
        log,
        "evidence_collected",
        fingerprint=event.fingerprint,
        host=host,
        probes=[e["probe"] for e in evidence],
        failed=failed,
    )
    await store.update(
        incident_id,
        event="evidence collected",
        detail=f"{len(evidence) - len(failed)}/{len(evidence)} probes succeeded",
        evidence=evidence,
    )
    return {"evidence": evidence}
