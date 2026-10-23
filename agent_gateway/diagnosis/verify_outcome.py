"""Did the remediation actually help?

Executing a command is not the same as resolving an incident. After a remediation the agent waits
for the metric window to move past the fault and queries again, so the incident records whether the
host recovered rather than only what was run.
"""

import asyncio
import os

from pydantic import BaseModel

from tools_client import call_tool

# node_exporter is scraped every 15s and the alert rule averages over a minute; a shorter wait
# would read a window that still contains the fault.
SETTLE_SECONDS = float(os.environ.get("VERIFY_SETTLE_SECONDS", 75))
RECOVERED_BELOW = 80.0

CPU_USAGE = '100 - (avg by (hostname) (rate(node_cpu_seconds_total{{mode="idle", hostname="{host}"}}[1m])) * 100)'


class Outcome(BaseModel):
    recovered: bool
    cpu_percent: float | None = None
    detail: str


async def verify_recovery(host: str, settle_seconds: float = SETTLE_SECONDS) -> Outcome:
    await asyncio.sleep(settle_seconds)
    try:
        result = await call_tool("query_metrics", {"promql": CPU_USAGE.format(host=host)})
    except Exception as exc:
        return Outcome(recovered=False, detail=f"could not verify: {exc}")

    series = result.get("series") or []
    if not series:
        return Outcome(recovered=False, detail="no cpu samples returned after the remediation")

    cpu = float(series[0]["value"])
    recovered = cpu < RECOVERED_BELOW
    detail = (
        f"cpu is {cpu:.1f}%, back under the {RECOVERED_BELOW:.0f}% threshold"
        if recovered
        else f"cpu is still {cpu:.1f}%; the remediation ran but did not resolve the alert"
    )
    return Outcome(recovered=recovered, cpu_percent=cpu, detail=detail)
