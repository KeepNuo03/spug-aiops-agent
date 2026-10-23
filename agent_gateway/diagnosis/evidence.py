"""Turn collected evidence into prompt text.

Metric probes come back as raw samples — twenty points per series, each with its labels. Feeding
that to the model wastes tokens and reads worse than a summary, so series are reduced to current,
peak, average and direction. Command output is already dense and is kept as text, only truncated.
"""

from typing import Any

MAX_OUTPUT_LINES = 15


def _summarize_series(series: list[dict[str, Any]]) -> str:
    if not series:
        return "no data"

    lines = []
    for entry in series:
        host = entry["labels"].get("hostname", entry["labels"].get("instance", "?"))
        if "value" in entry:
            lines.append(f"{host}: {entry['value']:.2f}")
            continue

        values = [s["value"] for s in entry.get("samples", [])]
        if not values:
            lines.append(f"{host}: no samples")
            continue
        trend = "rising" if values[-1] > values[0] * 1.1 else "falling" if values[-1] < values[0] * 0.9 else "steady"
        lines.append(
            f"{host}: current {values[-1]:.1f}, peak {max(values):.1f}, "
            f"average {sum(values) / len(values):.1f}, {trend} over {len(values)} samples"
        )
    return "\n".join(lines)


def _summarize_command(result: dict[str, Any]) -> str:
    if result.get("rejected"):
        return f"command rejected: {result['rejected']}"
    output = result.get("output", "")
    lines = output.splitlines()
    if len(lines) > MAX_OUTPUT_LINES:
        lines = lines[:MAX_OUTPUT_LINES] + [f"... ({len(output.splitlines()) - MAX_OUTPUT_LINES} more lines)"]
    return "\n".join(lines) or "no output"


def render_evidence(evidence: list[dict[str, Any]]) -> str:
    """Prompt-ready text. Failed probes are listed too, so the model can see what is missing."""
    blocks = []
    for item in evidence:
        if "error" in item:
            blocks.append(f"### {item['probe']}\nUNAVAILABLE: {item['error']}")
            continue
        result = item["result"]
        if item["tool"] == "query_metrics":
            body = f"query: {result['query']}\n{_summarize_series(result['series'])}"
        else:
            body = f"$ {result['command']}\n{_summarize_command(result)}"
        blocks.append(f"### {item['probe']}\n{body}")
    return "\n\n".join(blocks)


def evidence_text(evidence: list[dict[str, Any]]) -> str:
    """Everything the probes returned as one searchable string, for cross-checking the answer."""
    parts = []
    for item in evidence:
        result = item.get("result")
        if isinstance(result, dict):
            parts.append(str(result.get("output", "")))
            parts.append(str(result.get("series", "")))
    return "\n".join(parts)
