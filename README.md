# spug-aiops-agent

[![CI](https://github.com/KeepNuo03/spug-aiops-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/KeepNuo03/spug-aiops-agent/actions/workflows/ci.yml)

End-to-end AIOps agent: alert event → intent classification → multi-agent routing → MCP tool-driven diagnosis → HITL-gated remediation → online monitoring + offline evaluation loop.

Built on top of the [Spug](https://github.com/openspug/spug) ops platform (SSH execution / notification channels) and a Prometheus metrics stack.

## Status

Work in progress. The first milestone is the thinnest end-to-end slice for the `cpu_high` scenario; other modules are still placeholders.

- [x] Local lab: Spug + Prometheus + Alertmanager + lab host, fault injection through Spug
- [x] Agent Gateway receives and normalizes Alertmanager webhooks
- [x] CI: lint, format check, tests
- [x] Rule-based intent classification
- [x] MCP tools (`query_metrics`, `exec_command`) wired into a fixed route that collects evidence
- [ ] LLM diagnosis
- [ ] Then: HITL, other intents, memory, tool retry, evaluation

## Architecture

```
Alertmanager Webhook ─┐
Spug Alarm Query API ─┼─→ Intent Classifier (rules + LLM) ─→ Supervisor Router
Chat Entry            ─┘                                         │
                                    ┌────────────────────────────┼────────────────────────────┐
                                    ▼                             ▼                             ▼
                             Monitor Agent                 Diagnose Agent                 Fix / Execute / Notify Agent
                             (metrics/logs/alarms)         (root cause analysis)          (remediation decision → HITL approval → Spug SSH exec → notify)
                                    │                             │                             │
                                    └─────────────────────────────┴─────────────────────────────┘
                                                          MCP Server
                                        (query_metrics / query_logs / exec_command /
                                         get_host_info / list_alarms / send_notify / search_runbook)
```

## Directory Structure

```
spug-aiops-agent/
├── mcp_server/          # MCP tool layer: Prometheus / Spug / Loki / runbook retrieval tools
├── agent_gateway/        # Agent orchestration layer (FastAPI + LangGraph) + standalone Web UI
│   ├── graph/            # Supervisor + sub-agents (monitor/diagnose/fix/execute/notify)
│   ├── intent/           # Intent classification (rule engine + LLM few-shot)
│   ├── memory/           # Working memory (Redis) / conversation memory (sliding window) / episodic memory (Chroma)
│   ├── safety/           # Command safety policy + HITL human approval
│   └── observability/    # Structured logging / Prometheus instrumentation / feedback loop
├── eval/                 # Offline evaluation: test cases + LLM-as-Judge + release gate
├── fault_injection/      # Fault injection scripts (for eval data collection)
├── prometheus/           # Prometheus / Alertmanager configuration
└── runbooks/             # Remediation knowledge base (RAG data source)
```

## Quick Start

```bash
cp .env.example .env    # fill in LLM API key, Spug URL, etc.
docker compose up -d    # start Prometheus / Alertmanager / Redis and other dependencies
```

`docker compose up -d` starts everything: infrastructure, the lab, `mcp_server` and `agent_gateway`.

### Local Lab

| Component | Address | Notes |
|-----------|---------|-------|
| Spug | http://localhost:8080 | `admin` / `spug.dev` (local dev only) |
| Prometheus | http://localhost:9090 | scrapes `lab-host:9100` |
| Alertmanager | http://localhost:9093 | webhook → `agent_gateway` |
| Agent Gateway | http://localhost:8001 | `POST /webhook/alertmanager`, `GET /healthz` |
| MCP Server | http://localhost:8765/mcp | `query_metrics`, `exec_command` (read-only commands only) |
| lab-host | SSH `localhost:2222` | Ubuntu + sshd + stress-ng + node_exporter; registered in Spug as `lab-host` via `host.docker.internal:2222` |

Verify the full alert path:

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
# Register lab-host in Spug (or re-verify it after the environment is rebuilt)
.venv/Scripts/python lab/spug_register_host.py
# Run a command on lab-host through Spug's API
.venv/Scripts/python lab/spug_exec_smoke.py lab-host "uptime"
# Inject a CPU fault through Spug; HostHighCpuUsage fires after ~2 minutes
.venv/Scripts/python lab/spug_exec_smoke.py lab-host "setsid nohup stress-ng --cpu 0 --timeout 150s >/dev/null 2>&1 < /dev/null &"
docker logs -f aiops-agent-gateway
```

After editing `prometheus/alertmanager.yml`, reload it with `curl -X POST http://localhost:9093/-/reload`.

### Tests and Lint

CI runs the same three checks on every push to `main` and every pull request:

```bash
.venv/Scripts/ruff check .            # lint (add --fix to auto-fix)
.venv/Scripts/ruff format --check .   # formatting (drop --check to reformat)
.venv/Scripts/python -m pytest
```

A real Alertmanager payload captured from the lab is kept in `tests/fixtures/`.

Spug itself is a standalone runtime dependency and must be deployed separately (see the [official Spug install docs](https://ops.spug.cc/docs/install-docker)). This repo calls it over HTTP only and does not include or modify its source code.

## License

This project (spug-aiops-agent) is licensed under [Apache 2.0](LICENSE).

This project depends on [Spug](https://github.com/openspug/spug) (AGPL-3.0) at runtime,
but **does not include or modify** any of Spug's source code — it is called exclusively via HTTP API.
Spug itself remains under its original AGPL-3.0 license.
