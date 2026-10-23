import pytest

from diagnosis.models import RemediationAction
from safety.hitl import build_request
from safety.risk import classify, render_command

EVIDENCE = "  PID COMMAND   %CPU\n  344 stress-ng  100\n  339 stress-ng  100"


def kill(pid):
    return RemediationAction(action="kill", pid=pid, reason="stop the load generator")


def test_kill_of_a_pid_seen_in_evidence_is_executable():
    risk, blocked = classify(kill(344), EVIDENCE)
    assert risk == "dangerous"
    assert blocked is None


def test_kill_of_a_pid_absent_from_evidence_is_forbidden():
    risk, blocked = classify(kill(9999), EVIDENCE)
    assert risk == "forbidden"
    assert "does not appear" in blocked


@pytest.mark.parametrize("pid", [1, 7, 9])
def test_system_pids_are_forbidden(pid):
    risk, blocked = classify(kill(pid), f"pid {pid} is here")
    assert risk == "forbidden"
    assert "system process" in blocked


def test_kill_without_a_pid_is_forbidden():
    risk, blocked = classify(RemediationAction(action="kill", reason="no pid"), EVIDENCE)
    assert risk == "forbidden"


def test_manual_actions_are_never_executed_by_the_agent():
    action = RemediationAction(action="manual", command="systemctl restart nginx", reason="restart it")
    risk, blocked = classify(action, EVIDENCE)
    assert risk == "safe"
    assert "yourself" in blocked


def test_command_is_rendered_from_the_pid_not_the_model():
    assert render_command(kill(344)) == "kill -TERM 344"


def by_name(name):
    return RemediationAction(action="kill_by_name", process_name=name, reason="all of them must go")


def test_kill_by_name_seen_in_evidence_is_executable():
    risk, blocked = classify(by_name("stress-ng"), EVIDENCE)
    assert risk == "dangerous"
    assert blocked is None
    assert render_command(by_name("stress-ng")) == "pkill -TERM -x stress-ng"


@pytest.mark.parametrize("name", ["sshd", "systemd", "SSHD"])
def test_protected_processes_are_forbidden(name):
    risk, blocked = classify(by_name(name), f"1 {name} 0.0")
    assert risk == "forbidden"
    assert "protected" in blocked


def test_name_absent_from_evidence_is_forbidden():
    risk, blocked = classify(by_name("mysqld"), EVIDENCE)
    assert risk == "forbidden"
    assert "does not appear" in blocked


@pytest.mark.parametrize("name", ["stress-ng; rm -rf /", "$(whoami)", "a b", "", "x" * 40])
def test_names_that_are_not_plain_tokens_are_forbidden(name):
    risk, blocked = classify(by_name(name), f"evidence mentions {name}")
    assert risk == "forbidden"
    with pytest.raises(ValueError):
        render_command(by_name(name))


def test_only_kill_actions_can_be_rendered():
    with pytest.raises(ValueError):
        render_command(RemediationAction(action="manual", command="rm -rf /", reason="no"))


def test_request_marks_each_action(make_event):
    request = build_request(
        "incident-1",
        "lab-host",
        "stress-ng saturates the cpu",
        [kill(344), kill(1), RemediationAction(action="manual", command="dmesg", reason="check kernel log")],
        EVIDENCE,
    )
    executable = [a.executable for a in request.actions]
    assert executable == [True, False, False]
    assert request.actions[0].command == "kill -TERM 344"
    assert request.actions[2].command == "dmesg"


def test_request_expires(make_event):
    request = build_request("incident-1", "lab-host", "cause", [kill(344)], EVIDENCE)
    assert (request.expires_at - request.requested_at).total_seconds() == 30 * 60
