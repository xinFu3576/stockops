# Pipeline — 端到端调度

## 一次完整跑批的状态图

\`\`\`mermaid
stateDiagram-v2
  [*] --> CalendarGate
  CalendarGate --> Fetch: is_trading_day
  CalendarGate --> [*]: skip (non-trading)

  state Fetch {
    [*] --> MarketDataAgent
    MarketDataAgent --> NewsSentimentAgent
    NewsSentimentAgent --> AltDataAgent
    AltDataAgent --> [*]
  }

  Fetch --> Feature
  state Feature {
    [*] --> FactorAgent
    FactorAgent --> SentimentAgent
    SentimentAgent --> ChipsAgent
    ChipsAgent --> PITGuard
    PITGuard --> [*]: verified
  }

  Feature --> Analysts
  state Analysts <<fork>>
  Analysts --> FundamentalAnalyst
  Analysts --> TechnicalAnalyst
  Analysts --> SentimentAnalyst
  Analysts --> MacroEventAnalyst

  FundamentalAnalyst --> Debate
  TechnicalAnalyst --> Debate
  SentimentAnalyst --> Debate
  MacroEventAnalyst --> Debate

  state Debate {
    [*] --> Bull
    Bull --> Bear
    Bear --> Bull: round < max
    Bear --> [*]: round == max
  }

  Debate --> ResearchManager
  ResearchManager --> MemoryLookup: fetch past decisions + reflections
  MemoryLookup --> Backtest
  Backtest --> Compliance
  Compliance --> Risk
  Risk --> Trader: pass or downsize
  Risk --> Report: block
  Trader --> Execution
  Execution --> Report
  Report --> Persist
  Persist --> [*]
\`\`\`

## 关键设计点

### 1) 交易日历闸门（D7）
- Orchestrator 第一步查交易日历（akshare 或 tradingcalendar 库），非交易日直接短路，节省 LLM 额度。
- 支持 --force 覆盖，用于回测重跑。

### 2) 并行 Analyst，串行 Debate
- 4 位 Analyst 并行跑（asyncio.gather），彼此不知道对方结论，避免锚定。
- Bull / Bear 串行辩论，每轮读全部 Verdict + 上一轮对话。

### 3) 断点续跑（D7）
- LangGraph 的 SqliteSaver 存 checkpoint 到 \`memory/checkpoints/<ticker>_<date>.db\`。
- 失败重跑：\`--resume\`；清除：\`--clear-checkpoints\`。

### 4) 决策记忆闭环（D8）
- ResearchManager 前置：\`MemoryAgent.query(ticker, k=3)\`，把最近 3 次同标的决策 + 反思注入 prompt。
- Persist 后：\`MemoryAgent.write(Decision)\`。
- 定时任务：ReflectionAgent 每天扫 T-N 到 T-1 的记录，回填实际收益 + 生成反思。

### 5) 双模型分流
- **deep_llm**（GPT-5.5 / Claude 4.6）：ResearchManager、辩论、反思。
- **quick_llm**（GPT-5.4-mini / DeepSeek）：SentimentAgent、Analyst 初评、Report 摘要。
- 每个 Agent 声明自己需要哪一档，Orchestrator 注入。

### 6) 失败降级策略
| 组件 | 主 | 备 | 兜底 |
|---|---|---|---|
| 行情源 | TickFlow | AkShare | Baostock / YFinance |
| 新闻源 | Anspire | SerpAPI | Tavily / SearXNG |
| LLM | GPT-5.5 | Claude 4.6 | DeepSeek 本地 Ollama |
| 通知 | 企业微信 | Telegram | 邮件 |

### 7) 三种运行模式（D6）
| mode | 数据 | LLM | 回测 | 下单 |
|---|---|---|---|---|
| \`dry-run\` | 真实 | 真实 | 真实 | ✗（只出报告） |
| \`paper\` | 真实 | 真实 | 真实 | 模拟盘 |
| \`live\` | 真实 | 真实 | 真实 | 真实盘 + 人工二次确认 |

### 8) 成本控制
- 每 Agent tag 到 ObservabilityAgent，日报显式列出：
  - 每个 Agent 的调用次数、token、费用
  - 单个 ticker 端到端成本
  - 本周累计成本 vs 预算

## 触发方式

- **GitHub Actions**：workflow 每工作日 09:15（收盘前预警）和 18:00（收盘后决策）触发。
- **本地 cron**：\`crontab -e\` 加 \`0 18 * * 1-5 cd /path && python -m core.orchestrator run\`。
- **手动**：\`python -m core.orchestrator run --tickers 600519.SS,AAPL --date 2026-07-11\`。
- **CI 回测**：PR 触发全量回测比对，防止改坏。
