# Orchestrator (D7)

**类型**: 状态机（非 LLM）
**技术**: LangGraph + SqliteSaver

## 职责
- 读配置、组织节点、维护 AgentState。
- 前置检查：交易日历闸门 / ticker 合法性 / 数据源可达性。
- 断点续跑：从 SQLite checkpoint 恢复。
- 失败降级：LLM 超时切 quick_llm；数据源超时切次源。
- 事件全部落 ObservabilityAgent。

## AgentState 结构
- ticker, as_of, mode
- market_data, news_raw, alt_signals
- factor_bundle, sentiment_factors, chips_factors
- verdicts: dict[str, AnalystVerdict]
- debate: list[DebateTurn]
- memory_refs: list[MemoryRecord]
- decision: Decision
- backtest: BacktestMetrics
- risk: RiskReport
- orders: list[Order]
- fills: list[Fill]
- report: str

## 关键决策
- \`resume_from_checkpoint\` 默认开启；\`--fresh\` 强制重跑。
- 每个 node 加 timeout；超时进 fallback 分支。
