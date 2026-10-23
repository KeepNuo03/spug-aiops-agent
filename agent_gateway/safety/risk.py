"""Risk tiers for proposed actions, and what the agent is allowed to run.

Executing anything is gated twice: a human approves it, and the action must be one the agent can
express as a structured command. Killing a pid or an exact process name are the only such actions —
everything else is shown to the engineer to run themselves. A target that never appeared in the
evidence is treated as unverified and loses its approval button, the same rule the diagnosis
cross-check applies.
"""

import re
from typing import Literal

from diagnosis.models import RemediationAction

Risk = Literal["safe", "dangerous", "forbidden"]

# Pids below this belong to init and the container's own supervisor; killing them takes the host
# down rather than fixing it.
LOWEST_KILLABLE_PID = 10

# Killing these takes the host out of reach, or kills the agent's own way back in.
PROTECTED_PROCESSES = frozenset(
    {"init", "systemd", "sshd", "dockerd", "containerd", "kthreadd", "bash", "sh", "supervisord", "spug"}
)

# Rendered into a command, so the name has to be a plain token and nothing else.
PROCESS_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,31}$")


def classify(action: RemediationAction, evidence_blob: str) -> tuple[Risk, str | None]:
    """Risk tier plus why it cannot be executed, if it cannot."""
    if action.action == "kill":
        if action.pid is None:
            return "forbidden", "no pid given"
        if action.pid < LOWEST_KILLABLE_PID:
            return "forbidden", f"pid {action.pid} is a system process"
        if str(action.pid) not in evidence_blob:
            return "forbidden", f"pid {action.pid} does not appear in the collected evidence"
        return "dangerous", None

    if action.action == "kill_by_name":
        name = action.process_name or ""
        if not PROCESS_NAME.match(name):
            return "forbidden", "process name is missing or not a plain name"
        if name.lower() in PROTECTED_PROCESSES:
            return "forbidden", f"'{name}' is a protected process"
        if name not in evidence_blob:
            return "forbidden", f"'{name}' does not appear in the collected evidence"
        return "dangerous", None

    return "safe", "the agent only executes kill actions; run this one yourself"


def render_command(action: RemediationAction) -> str:
    """The shell command for an approved action. Built here, never taken from the model."""
    if action.action == "kill" and action.pid is not None:
        return f"kill -TERM {int(action.pid)}"
    if action.action == "kill_by_name" and action.process_name and PROCESS_NAME.match(action.process_name):
        return f"pkill -TERM -x {action.process_name}"
    raise ValueError("only validated kill actions can be rendered")
