"""MCP Server: the tools the agent uses to inspect the fleet.

Only read-only tools exist so far. `exec_command` enforces the command policy itself, so a caller
(including an LLM-generated command) cannot run remediation through it.
"""

import os
from typing import Any

from mcp.server import MCPServer
from pydantic import BaseModel

from tools.command_policy import CommandRejected, ensure_read_only
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


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=int(os.environ.get("MCP_PORT", 8765)))
