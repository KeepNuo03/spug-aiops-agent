"""Spug client: host inventory and command execution over Spug's HTTP + WebSocket API.

Spug executes asynchronously: POST creates the task, a WebSocket subscription streams the output,
PATCH dispatches it to the worker, and the stream ends with the exit status.
"""

import json
import os
import re

import httpx
import websocket

SPUG_URL = os.environ.get("SPUG_BASE_URL", "http://host.docker.internal:8080")
USERNAME = os.environ.get("SPUG_USERNAME", "admin")
PASSWORD = os.environ.get("SPUG_PASSWORD", "spug.dev")

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
# Spug frames the real output with its own banner and timing line.
SPUG_DECORATION = re.compile(r"^(### .*|\*\* .* \*\*)$")


def _clean(output: str) -> str:
    lines = [line.rstrip() for line in ANSI.sub("", output).replace("\r\n", "\n").split("\n")]
    # Only blank lines are trimmed: leading spaces keep table columns aligned.
    return "\n".join(line for line in lines if not SPUG_DECORATION.match(line.strip())).strip("\n")


class SpugClient:
    def __init__(self, base_url: str = SPUG_URL, username: str = USERNAME, password: str = PASSWORD) -> None:
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._token: str | None = None

    def _call(self, method: str, path: str, *, auth: bool = True, **kwargs) -> dict | list | str:
        headers = {"X-Token": self._login()} if auth else {}
        with httpx.Client(timeout=60) as client:
            body = client.request(method, f"{self._base_url}/api{path}", headers=headers, **kwargs).json()
        if body.get("error"):
            raise RuntimeError(f"spug {method} {path}: {body['error']}")
        return body["data"]

    def _login(self) -> str:
        if self._token is None:
            data = self._call(
                "POST",
                "/account/login/",
                auth=False,
                json={"username": self._username, "password": self._password, "type": "default"},
            )
            self._token = data["access_token"]
        return self._token

    def _host_id(self, host_name: str) -> int:
        for host in self._call("GET", "/host/"):
            if host["name"] == host_name:
                return host["id"]
        raise RuntimeError(f"host '{host_name}' is not registered in Spug")

    def exec_command(self, host_name: str, command: str, timeout: float = 60) -> dict:
        host_id = self._host_id(host_name)
        token = self._login()
        task = self._call("POST", "/exec/do/", json={"host_ids": [host_id], "command": command})

        ws_url = f"{self._base_url.replace('http', 'ws', 1)}/api/ws/subscribe/{task}/?x-token={token}"
        ws = websocket.create_connection(ws_url, timeout=timeout)
        try:
            self._call("PATCH", "/exec/do/", json={"token": task})
            output, status = [], None
            while status is None:
                ws.send("ping")
                message = ws.recv()
                if message == "pong":
                    continue
                event = json.loads(message)
                if "data" in event:
                    output.append(event["data"])
                if "status" in event:
                    status = event["status"]
        finally:
            ws.close()

        return {"host": host_name, "command": command, "exit_status": status, "output": _clean("".join(output))}
