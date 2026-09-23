import pytest

from tools.command_policy import CommandRejected, ensure_read_only


@pytest.mark.parametrize(
    "command",
    [
        "uptime",
        "top -bn1",
        "top -bn1 | head -20",
        "ps -eo pid,comm,%cpu --sort=-%cpu | head -10",
        "cat /proc/loadavg",
        "/usr/bin/free -m",
    ],
)
def test_read_only_commands_are_allowed(command):
    ensure_read_only(command)


@pytest.mark.parametrize(
    "command",
    [
        "kill -9 1234",
        "systemctl restart nginx",
        "rm -rf /tmp/data",
        "uptime; kill -9 1234",
        "uptime && kill -9 1234",
        "top -bn1 > /tmp/out",
        "echo $(kill -9 1234)",
        "uptime `kill -9 1234`",
        "top -bn1 | xargs kill",
        "",
        "   ",
        "uptime |",
    ],
)
def test_dangerous_commands_are_rejected(command):
    with pytest.raises(CommandRejected):
        ensure_read_only(command)
