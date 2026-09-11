"""Agent Gateway FastAPI 入口。

职责:
- 接收 Alertmanager Webhook / Spug 告警查询结果 / Chat 用户输入
- 调 intent.classifier 做意图识别
- 驱动 graph.supervisor 完成多 Agent 路由
- 通过 SSE 向 frontend/ 推流对话与执行状态

TODO: 实现 FastAPI app、/webhook/alertmanager、/chat(SSE)、/hitl/approve 等路由。
"""
