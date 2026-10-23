from diagnosis.evidence import evidence_text, render_evidence

SAMPLES = [{"ts": 0, "value": 10.0}, {"ts": 30, "value": 55.0}, {"ts": 60, "value": 99.0}]

EVIDENCE = [
    {
        "probe": "cpu_usage_trend",
        "tool": "query_metrics",
        "result": {"query": "cpu", "series": [{"labels": {"hostname": "lab-host"}, "samples": SAMPLES}]},
    },
    {
        "probe": "load1",
        "tool": "query_metrics",
        "result": {"query": "node_load1", "series": [{"labels": {"hostname": "lab-host"}, "value": 13.28}]},
    },
    {
        "probe": "top_processes",
        "tool": "exec_command",
        "result": {"command": "ps aux", "output": "  344 stress-ng 100", "exit_status": 0},
    },
]


def test_series_are_summarized_not_dumped():
    block = render_evidence(EVIDENCE)
    assert "current 99.0, peak 99.0, average 54.7, rising over 3 samples" in block
    # The raw samples must not reach the prompt.
    assert "'ts'" not in block and "55.0" not in block


def test_instant_values_are_rendered():
    assert "lab-host: 13.28" in render_evidence(EVIDENCE)


def test_command_output_is_kept_verbatim():
    assert "$ ps aux" in render_evidence(EVIDENCE)
    assert "344 stress-ng 100" in render_evidence(EVIDENCE)


def test_long_output_is_truncated():
    evidence = [
        {
            "probe": "top_snapshot",
            "tool": "exec_command",
            "result": {"command": "top", "output": "\n".join(f"line {i}" for i in range(40))},
        }
    ]
    block = render_evidence(evidence)
    assert "line 14" in block
    assert "line 20" not in block
    assert "25 more lines" in block


def test_failed_probe_is_shown_as_unavailable():
    block = render_evidence([{"probe": "load1", "tool": "query_metrics", "error": "prometheus unreachable"}])
    assert "UNAVAILABLE: prometheus unreachable" in block


def test_rejected_command_is_shown():
    evidence = [
        {
            "probe": "fix",
            "tool": "exec_command",
            "result": {"command": "kill -9 1", "rejected": "'kill' is not an allowed read-only command"},
        }
    ]
    assert "command rejected" in render_evidence(evidence)


def test_evidence_text_collects_output_for_cross_checking():
    assert "stress-ng" in evidence_text(EVIDENCE)
