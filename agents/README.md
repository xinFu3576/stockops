# agents/

每个 Agent 一张角色卡。文件名前缀=拓扑顺序：

- 00_orchestrator（编排器，非 LLM）
- 01-03 数据面（MarketData / News / Alt）
- 04-06 特征面（Factor / Sentiment / Chips）
- 10-13 4 位分析师
- 14-15 Bull / Bear
- 16 ResearchManager
- 20 Backtest
- 30-31 Risk / Compliance
- 40-42 Trader / Execution / Reporting
- 50-51 Memory / Reflection
- 60 Observability
