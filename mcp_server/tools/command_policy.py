"""Command safety policy.

This milestone only runs a fixed set of diagnostic commands, but `exec_command` reaches real hosts
through Spug, so the tool enforces the policy itself rather than trusting its caller. Remediation
commands (kill, systemctl, rm, ...) are rejected until human-in-the-loop approval exists.
"""

import re
import shlex

READ_ONLY_COMMANDS = frozenset(
    {
        "awk",
        "cat",
        "cut",
        "date",
        "df",
        "du",
        "free",
        "grep",
        "head",
        "hostname",
        "iostat",
        "ps",
        "sed",
        "sort",
        "tail",
        "top",
        "uname",
        "uniq",
        "uptime",
        "vmstat",
        "wc",
        "who",
    }
)

# Anything that chains, redirects or substitutes: only plain pipelines are allowed.
FORBIDDEN_SHELL_SYNTAX = re.compile(r"[;&<>`\n]|\$\(")

# Pids below this belong to init and the container's own supervisor; killing them takes the host
# down rather than fixing it.
LOWEST_KILLABLE_PID = 10

# Killing these takes the host out of reach, or kills the agent's own way back in.
PROTECTED_PROCESSES = frozenset(
    {"init", "systemd", "sshd", "dockerd", "containerd", "kthreadd", "bash", "sh", "supervisord", "spug"}
)

# Rendered into a command, so the name has to be a plain token and nothing else.
PROCESS_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,31}$")


def ensure_killable_name(name: str) -> None:
    """Raise CommandRejected unless this process name is safe to render into a pkill."""
    if not PROCESS_NAME.match(name or ""):
        raise CommandRejected("process name is missing or not a plain name")
    if name.lower() in PROTECTED_PROCESSES:
        raise CommandRejected(f"'{name}' is a protected process")


class CommandRejected(ValueError):
    pass


def ensure_read_only(command: str) -> None:
    """Raise CommandRejected unless the command is a pipeline of allow-listed read-only commands."""
    if not command.strip():
        raise CommandRejected("empty command")
    if FORBIDDEN_SHELL_SYNTAX.search(command):
        raise CommandRejected("command chaining, redirection and substitution are not allowed")

    for segment in command.split("|"):
        try:
            tokens = shlex.split(segment)
        except ValueError as exc:
            raise CommandRejected(f"could not parse command: {exc}") from exc
        if not tokens:
            raise CommandRejected("empty pipeline segment")
        program = tokens[0].rsplit("/", 1)[-1]
        if program not in READ_ONLY_COMMANDS:
            raise CommandRejected(f"'{program}' is not an allowed read-only command")
