"""Register lab-host in Spug, or re-verify it so Spug re-installs its SSH key (idempotent).

Usage: python lab/spug_register_host.py
"""

import os
import sys

import httpx

from spug_exec_smoke import PASSWORD, USERNAME, api

HOST = {
    "name": "lab-host",
    "hostname": "host.docker.internal",
    "port": 2222,
    "username": "root",
    "password": os.environ.get("LAB_HOST_PASSWORD", "aiops-lab"),
    "desc": "AIOps lab target host",
}


def main() -> None:
    with httpx.Client(timeout=60) as client:
        auth = api(
            client, "POST", "/account/login/", json={"username": USERNAME, "password": PASSWORD, "type": "default"}
        )["access_token"]
        existing = next((h for h in api(client, "GET", "/host/", auth) if h["name"] == HOST["name"]), None)
        group_ids = (
            existing["group_ids"] if existing else [api(client, "GET", "/host/group/", auth)["treeData"][0]["key"]]
        )
        body = {**HOST, "group_ids": group_ids, **({"id": existing["id"]} if existing else {})}
        host = api(client, "POST", "/host/", auth, json=body)
    action = "re-verified" if existing else "registered"
    print(f"{action} {host['name']} (id={host['id']}, verified={host['is_verified']})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
