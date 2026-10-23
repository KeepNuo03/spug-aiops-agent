"""MCP Server: the tools the agent uses to inspect the fleet.

Only read-only tools exist so far. `exec_command` enforces the command policy itself, so a caller
(including an LLM-generated command) cannot run remediation through it.
"""

import os
from typing import Any

from mcp.server import MCPServer
from pydantic import BaseModel

from tools.command_policy import (
    LOWEST_KILLABLE_PID,
    CommandRejected,
    ensure_killable_name,
    ensure_read_only,
)
from tools.prometheus_tools import query_instant, query_range
from tools.spug_tools import SpugClient

mcp = MCPServer("spug-aiops-tools")
spug = SpugClient()


class MetricsResult(BaseModel):
    query: str
    series: list[dict[str, Any]]


class CommandResult(BaseModel):
    host: str
    command: str
    exit_status: int | None = None
    output: str = ""
    rejected: str | None = None


@mcp.tool()
def query_metrics(promql: str, range_minutes: int = 0, step: str = "30s") -> MetricsResult:
    """Query Prometheus with PromQL.

    Args:
        promql: the query, e.g. 100 - (avg by (hostname) (rate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)
        range_minutes: 0 for the current value, or how many minutes back to sample
        step: sample interval when range_minutes is set
    """
    if range_minutes > 0:
        return MetricsResult(query=promql, series=query_range(promql, minutes=range_minutes, step=step))
    return MetricsResult(query=promql, series=query_instant(promql))


@mcp.tool()
def exec_command(host: str, command: str) -> CommandResult:
    """Run a read-only diagnostic command on a Spug-managed host over SSH.

    Only read-only commands are permitted (top, ps, df, free, ...); anything that could change the
    host is rejected. Args: host is the host name registered in Spug; command is a shell pipeline.
    """
    try:
        ensure_read_only(command)
    except CommandRejected as exc:
        return CommandResult(host=host, command=command, rejected=str(exc))
    return CommandResult(**spug.exec_command(host, command))


@mcp.tool()
def kill_process(host: str, pid: int) -> CommandResult:
    """Send SIGTERM to one process on a Spug-managed host. Requires human approval upstream.

    Takes a pid rather than a command so no caller can turn it into arbitrary shell, and refuses
    the low pids that belong to system processes.
    """
    if pid < LOWEST_KILLABLE_PID:
        return CommandResult(host=host, command=f"kill -TERM {pid}", rejected=f"pid {pid} is a system process")
    return CommandResult(**spug.exec_command(host, f"kill -TERM {int(pid)}"))


@mcp.tool()
def kill_by_name(host: str, process_name: str) -> CommandResult:
    """Send SIGTERM to every process with this exact name. Requires human approval upstream.

    For a workload that runs as many identical processes, where killing one pid achieves nothing.
    The name must be a plain token and must not name a process the host depends on.
    """
    try:
        ensure_killable_name(process_name)
    except CommandRejected as exc:
        return CommandResult(host=host, command=f"pkill -TERM -x {process_name}", rejected=str(exc))
    return CommandResult(**spug.exec_command(host, f"pkill -TERM -x {process_name}"))


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=int(os.environ.get("MCP_PORT", 8765)))
