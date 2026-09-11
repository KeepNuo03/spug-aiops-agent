# spug-aiops-agent

End-to-end AIOps agent: alert event → intent classification → multi-agent routing → MCP tool-driven diagnosis → HITL-gated remediation → online monitoring + offline evaluation loop.

Built on top of the [Spug](https://github.com/openspug/spug) ops platform (SSH execution / notification channels) and a Prometheus metrics stack. Full design doc: [`docs/design.md`](docs/design.md) (if included in this repo).

> **Status**: scaffolding stage. The directory structure is in place; each module is a placeholder and end-to-end wiring is not yet complete.

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

Spug itself is a standalone runtime dependency and must be deployed separately (see the [official Spug install docs](https://ops.spug.cc/docs/install-docker)). This repo calls it over HTTP only and does not include or modify its source code.

## License

This project (spug-aiops-agent) is licensed under [Apache 2.0](LICENSE).

This project depends on [Spug](https://github.com/openspug/spug) (AGPL-3.0) at runtime,
but **does not include or modify** any of Spug's source code — it is called exclusively via HTTP API.
Spug itself remains under its original AGPL-3.0 license.
