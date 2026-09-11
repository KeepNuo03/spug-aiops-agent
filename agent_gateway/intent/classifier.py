"""双层意图分类器。

Layer 1: 规则引擎(告警关键词/指标阈值 → 意图模板,确定性、零 token 成本)
Layer 2: LLM few-shot 分类(规则未命中的自然语言指令)

TODO: 实现 rule_classify() / llm_classify() / classify_intent() 及置信度路由。
"""
