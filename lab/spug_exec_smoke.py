"""Smoke test: run a shell command on a Spug-managed host through Spug's HTTP + WebSocket API.

Spug exec is asynchronous:
  1. POST  /api/exec/do/                 -> task token
  2. WS    /api/ws/subscribe/<token>/?x-token=<auth>  (server drains Redis pub/sub on each client message)
  3. PATCH /api/exec/do/ {token}         -> dispatch to worker
  4. read {"key": host_id, "data": ...} chunks until {"key": host_id, "status": exit_code}

Usage: python lab/spug_exec_smoke.py [host_name] [command]
"""
import json
import os
import re
import sys

import httpx
import websocket

SPUG_URL = os.environ.get("SPUG_BASE_URL", "http://localhost:8080")
USERNAME = os.environ.get("SPUG_USERNAME", "admin")
PASSWORD = os.environ.get("SPUG_PASSWORD", "spug.dev")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def api(client, method, path, token=None, **kwargs):
    headers = {"X-Token": token} if token else {}
    resp = client.request(method, f"{SPUG_URL}/api{path}", headers=headers, **kwargs).json()
    if resp.get("error"):
        raise RuntimeError(f"{method} {path}: {resp['error']}")
    return resp["data"]


def run(host_name: str, command: str) -> int:
    with httpx.Client(timeout=30) as client:
        auth = api(client, "POST", "/account/login/",
                   json={"username": USERNAME, "password": PASSWORD, "type": "default"})["access_token"]
        host = next(h for h in api(client, "GET", "/host/", auth) if h["name"] == host_name)
        task = api(client, "POST", "/exec/do/", auth, json={"host_ids": [host["id"]], "command": command})

        ws_url = SPUG_URL.replace("http", "ws", 1) + f"/api/ws/subscribe/{task}/?x-token={auth}"
        ws = websocket.create_connection(ws_url, timeout=60)
        api(client, "PATCH", "/exec/do/", auth, json={"token": task})

        output, status = [], None
        while status is None:
            ws.send("ping")
            msg = ws.recv()
            if msg == "pong":
                continue
            event = json.loads(msg)
            if "data" in event:
                output.append(ANSI.sub("", event["data"]))
            if "status" in event:
                status = event["status"]
        ws.close()

    print("".join(output).replace("\r\n", "\n").strip())
    print(f"\n[exit status: {status}]")
    return status


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    name = sys.argv[1] if len(sys.argv) > 1 else "lab-host"
    cmd = sys.argv[2] if len(sys.argv) > 2 else "hostname && uptime && nproc"
    sys.exit(0 if run(name, cmd) == 0 else 1)
