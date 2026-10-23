from diagnosis.models import CulpritProcess, Diagnosis
from diagnosis.verify import verify

EVIDENCE = """  PID COMMAND         %CPU
  344 stress-ng        100
  339 stress-ng        100"""
PROBES = ["cpu_usage_trend", "top_processes"]


def make_diagnosis(**overrides) -> Diagnosis:
    defaults = dict(
        root_cause="stress-ng saturates every core",
        summary="Four stress-ng workers are pinning the CPU.",
        confidence=0.95,
        evidence_used=["top_processes"],
        culprit_process=CulpritProcess(name="stress-ng", pid=344, cpu_percent=100.0),
    )
    return Diagnosis(**{**defaults, **overrides})


def test_diagnosis_grounded_in_evidence_is_verified():
    report = verify(make_diagnosis(), EVIDENCE, PROBES)
    assert report.verified
    assert report.confidence == 0.95
    assert report.verification_note is None


def test_invented_process_is_caught():
    report = verify(make_diagnosis(culprit_process=CulpritProcess(name="mysqld", pid=344)), EVIDENCE, PROBES)
    assert not report.verified
    assert report.confidence == 0.0
    assert "mysqld" in report.verification_note


def test_invented_pid_is_caught():
    report = verify(make_diagnosis(culprit_process=CulpritProcess(name="stress-ng", pid=9999)), EVIDENCE, PROBES)
    assert not report.verified
    assert "9999" in report.verification_note


def test_citing_a_probe_that_never_ran_is_caught():
    report = verify(make_diagnosis(evidence_used=["kernel_trace"]), EVIDENCE, PROBES)
    assert not report.verified
    assert "kernel_trace" in report.verification_note


def test_diagnosis_without_a_culprit_can_still_verify():
    report = verify(make_diagnosis(culprit_process=None, confidence=0.3), EVIDENCE, PROBES)
    assert report.verified
    assert report.confidence == 0.3


def test_root_cause_and_suggestions_are_preserved():
    report = verify(make_diagnosis(culprit_process=CulpritProcess(name="ghost")), EVIDENCE, PROBES)
    assert report.root_cause == "stress-ng saturates every core"
    assert report.culprit_process.name == "ghost"
