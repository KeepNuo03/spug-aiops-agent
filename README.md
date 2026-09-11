# spug-aiops-agent

端到端 AIOps Agent:告警事件驱动 → 意图识别 → 多 Agent 路由 → MCP 工具调诊断 → HITL 安全修复 → 在线监控 + 离线评测闭环。

基于 [Spug](https://github.com/openspug/spug) 运维平台(SSH 执行 / 通知渠道)+ Prometheus 指标体系构建。完整设计文档见 [`docs/技术方案.md`](docs/技术方案.md)(如已放入本仓库)。

> **当前状态**:项目脚手架阶段,目录结构已搭建,各模块为占位实现,尚未完成端到端联调。

## 架构总览

```
Alertmanager Webhook ─┐
Spug 告警查询 API     ─┼─→ Intent Classifier (规则 + LLM) ─→ Supervisor Router
Chat 入口             ─┘                                         │
                                    ┌────────────────────────────┼────────────────────────────┐
                                    ▼                             ▼                             ▼
                             Monitor Agent                 Diagnose Agent                 Fix / Execute / Notify Agent
                             (查指标/日志/告警)              (根因分析)                     (修复决策 → HITL 审批 → Spug SSH 执行 → 通知)
                                    │                             │                             │
                                    └─────────────────────────────┴─────────────────────────────┘
                                                          MCP Server
                                        (query_metrics / query_logs / exec_command /
                                         get_host_info / list_alarms / send_notify / search_runbook)
```

## 目录结构

```
spug-aiops-agent/
├── mcp_server/          # MCP 工具层:Prometheus / Spug / Loki / Runbook 检索工具
├── agent_gateway/        # Agent 编排层(FastAPI + LangGraph)+ 独立 Web UI
│   ├── graph/            # Supervisor + 各子 Agent(monitor/diagnose/fix/execute/notify)
│   ├── intent/           # 意图识别(规则引擎 + LLM few-shot)
│   ├── memory/           # 工作记忆(Redis)/ 对话记忆(滑动窗口)/ 情景记忆(Chroma)
│   ├── safety/           # 命令安全策略 + HITL 人工审批
│   └── observability/    # 结构化日志 / Prometheus 埋点 / 反馈闭环
├── eval/                 # 离线评测:测试用例 + LLM-as-Judge + 发布门禁
├── fault_injection/      # 故障注入脚本(用于评测数据采集)
├── prometheus/           # Prometheus / Alertmanager 配置
└── runbooks/             # 修复知识库(RAG 数据源)
```

## 快速开始

```bash
cp .env.example .env    # 填入 LLM API Key、Spug 地址等
docker compose up -d    # 启动 Prometheus / Alertmanager / Redis 等依赖
```

Spug 本体作为独立运行时依赖,需单独部署(参考 [Spug 官方安装文档](https://ops.spug.cc/docs/install-docker)),本仓库通过 HTTP API 调用,不包含也不修改其源码。

## 许可证

本项目 (spug-aiops-agent) 使用 [Apache 2.0](LICENSE) 许可证。

本项目在运行时依赖 [Spug](https://github.com/openspug/spug)(AGPL-3.0),
但**不包含、不修改** Spug 的任何源代码,仅通过 HTTP API 调用。
Spug 本身的许可证仍为其原始的 AGPL-3.0。
