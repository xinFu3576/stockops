# 团队编制 (AGENTS.md)

## 团队拓扑

\`\`\`
              [Orchestrator: LangGraph 状态机]
                        │
     ┌──────────────────┼───────────────────────────┐
     ▼                  ▼                           ▼
 [D1 数据面]        [D2 特征面]                 [D3 策略面]
 MarketDataAgent    FactorAgent                 FundamentalAnalyst
 NewsSentimentAgent SentimentAgent              TechnicalAnalyst
 AltDataAgent       ChipsAgent                  SentimentAnalyst
                                                MacroEventAnalyst
                                                    │
                                          ┌─────────┴────────┐
                                          ▼                  ▼
                                    BullResearcher    BearResearcher
                                          │                  │
                                          └────────┬─────────┘
                                                   ▼
                                          ResearchManager
                                                   │
     ┌──────────────────┬──────────────────────────┼─────────────┐
     ▼                  ▼                          ▼             ▼
 [D4 回测面]       [D5 风控面]                [D6 执行面]   [D8 记忆面]
 BacktestAgent    RiskAgent                  Trader        MemoryAgent
                  ComplianceAgent            ExecutionAgent ReflectionAgent
                                             ReportingAgent
\`\`\`

## 完整 Agent 清单（14 个 + 1 编排器）

| # | Agent | 维度 | 类型 | 主要职责 | 关键输入 | 关键输出 |
|---|---|---|---|---|---|---|
| 0 | **Orchestrator** | D7 | 状态机 | 编排、断点续跑、交易日历闸门 | ticker, date, mode | 全链路 state |
| 1 | **MarketDataAgent** | D1 | 工具型 | 拉行情/K线/复权/停复牌 | ticker, window | OHLCV+adj+halted |
| 2 | **NewsSentimentAgent** | D1 | 工具型+LLM | 拉新闻、公告、研报，抽情绪 | ticker, window | news[], sentiment |
| 3 | **AltDataAgent** | D1 | 工具型 | 龙虎榜、大宗交易、股东变动、宏观 | ticker, window | alt_signals[] |
| 4 | **FactorAgent** | D2 | 工具型 | 计算技术+基本面因子（含 PIT 检查） | 行情+财报 | factors_pit[] |
| 5 | **SentimentAgent** | D2 | LLM | 把 news_raw 结构化为情绪因子 + 事件因子 | news[] | sentiment_factors |
| 6 | **ChipsAgent** | D2 | 工具型 | 筹码分布、机构持股、涨停原因（A 股特色） | 成交+龙虎榜 | chips_factors |
| 7 | **FundamentalAnalyst** | D3 | LLM | 基本面视角评级 | factors_pit + 财报 | verdict + rationale |
| 8 | **TechnicalAnalyst** | D3 | LLM | 技术面视角评级 | factors_pit + chips | verdict + rationale |
| 9 | **SentimentAnalyst** | D3 | LLM | 情绪面视角评级 | sentiment_factors | verdict + rationale |
| 10 | **MacroEventAnalyst** | D3 | LLM | 宏观+事件驱动视角评级 | alt_signals + macro | verdict + rationale |
| 11 | **BullResearcher / BearResearcher** | D3 | LLM | 对辩 N 轮，对每个论点交叉质证 | 4 份 verdict | debate_transcript |
| 12 | **ResearchManager** | D3 | LLM | 综合辩论结果，出结构化决策 | debate + 记忆 | Decision (Pydantic) |
| 13 | **BacktestAgent** | D4 | 工具型 | 用真实撮合模型回测 signal | Decision + 历史 | metrics + attribution |
| 14 | **RiskAgent** | D5 | 规则+LLM | 三级风控闸门（Order/Portfolio/Strategy） | Decision + 组合 | pass/block + reasons |
| 15 | **ComplianceAgent** | D5 | 规则 | 黑名单 / ST / 停牌 / 合规 | Decision | pass/block |
| 16 | **Trader** | D6 | LLM+规则 | 转成具体单据（品种、方向、数量、价位、止损） | Decision (已过风控) | Order 列表 |
| 17 | **ExecutionAgent** | D6 | 工具型 | 按 mode（dry/paper/live）执行 | Order 列表 | fills / simulation |
| 18 | **ReportingAgent** | D6 | LLM | 生成决策仪表盘 + 多通道推送 | 全部 state | dashboard.md + 推送状态 |
| 19 | **MemoryAgent** | D8 | 工具型 | 落盘决策日志、检索历史决策 | Decision, ticker | memory records |
| 20 | **ReflectionAgent** | D8 | LLM | T+N 后算实际收益 + 生成反思 | 历史 Decision + 现价 | reflection markdown |
| 21 | **ObservabilityAgent** | D9 | 横切 | 收集 trace、token、成本 | 所有事件 | trace records |

> Bull 和 Bear 合并算一行，故实际实现是 **14 个 LLM/工具 Agent + 1 个 Orchestrator + 1 个 Observability 横切**。

## 通信契约

- 所有 Agent 输入输出走 **Pydantic v2 schema**（见 [DATA_CONTRACT.md](DATA_CONTRACT.md)）。
- LLM Agent 强制 **structured output**（OpenAI / Claude 的原生 JSON schema 或 instructor 库）。
- 事件流经过 **共享 State**（LangGraph AgentState），不做点对点调用。
- 失败降级策略在 [PIPELINE.md](PIPELINE.md) 里定义。

## 阵容可调整点

- 想省成本：关掉 MacroEventAnalyst + 把 debate_rounds 从 2 调到 0，其它保留。
- 想加深研究：把辩论轮数拉到 3，或增设 QuantAnalyst（跑 qlib 因子模型）作为第五位分析师。
- 想做 A 股专精：增强 ChipsAgent，把龙虎榜 / 涨停原因 / 打板成功率作为专项因子。
- 想做美股 / 港股专精：增强 MacroEventAnalyst，接 FRED / Polymarket 事件。
