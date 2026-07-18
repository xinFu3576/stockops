# 设计框架：9 个维度（含"隐形关键点"）

调研自 GitHub 头部股票项目（TradingAgents 93k / Qlib / FinRL / daily_stock_analysis 57k / myhhub 13k / Ghostfolio / OpenBB / akshare / adata / TradeMaster 等），把常被忽略的关键点吸收后，压成 9 个维度。**每个维度对应一个或一组 Agent**。

---

## D1. 数据层 — 多源 + 降级 + Point-in-Time

**目标**：任何时刻可拿到"当时能看到的"行情、基本面、公告、新闻、龙虎榜、筹码、宏观。

**关键设计**
- **多源并联 + 优先级降级**：TickFlow → AkShare → Baostock → YFinance；同类字段做归一化 schema。
- **Point-in-Time 数据库**：公告日 ≠ 财报日，回测必须用 T 日"能看到"的数据。参考 qlib PIT。
- **API Key 池 + 熔断**：多 key 轮换 + 每源限流阈值；触发熔断自动切下一源。
- **交易日历前置闸门**：A/H/US 三地节假日感知；非交易日整个 pipeline 短路。
- **停复牌 / ST / 除权除息前复权**：数据层就处理干净，不甩给策略层。

**对应 Agent**：MarketDataAgent + NewsSentimentAgent + AltDataAgent

---

## D2. 特征 / 因子层 — 从"指标堆"升级为"因子体系"

**目标**：把 K 线 → 技术指标 → 因子 → 舆情情绪 → 中国特色因子（筹码、龙虎榜、涨停原因）都当一等公民管理。

**关键设计**
- **因子表达式引擎**（借鉴 qlib）：因子用类 SQL / DSL 声明，可版本化、可组合。
- **多类别并存**：价量因子 / 基本面因子 / 情绪因子 / 事件因子 / 中国特色因子（筹码分布、龙虎榜、机构持股）。
- **IC/IR 评估**：每个因子自带质量指标，防止拍脑袋堆指标。
- **未来函数守卫**：任何用到 T 日 close 的因子必须显式声明，进入 T+1 才能用于 signal。

**对应 Agent**：FactorAgent（技术+基本面因子）+ SentimentAgent（新闻/研报/舆情） + ChipsAgent（中国特色因子）

---

## D3. 策略层 — 4 类分析师 + 一个研究经理，多角色辩论

**目标**：不押注单一范式，把 **规则派 / 因子派 / 事件驱动派 / LLM 推理派** 都塞进来，由 Research Manager 决出最终评级。

**关键设计**（借鉴 TradingAgents）
- 4 类 Analyst 独立出结论：Fundamental / Technical / Sentiment / Macro-Event。
- Bull 研究员 vs Bear 研究员对辩 N 轮（可配置 max_debate_rounds）。
- Research Manager 汇总，输出**结构化决策**（Pydantic schema：评分 / 方向 / 置信度 / 关键论据 / 风险点 / 催化因素）。
- **双模型分流**：Deep-think LLM（复杂推理，如 GPT-5.5 / Claude 4.6）+ Quick-think LLM（成本敏感任务，如 GPT-5.4-mini）。

**对应 Agent**：FundamentalAnalyst / TechnicalAnalyst / SentimentAnalyst / MacroEventAnalyst / BullResearcher / BearResearcher / ResearchManager

---

## D4. 回测层 — 撮合 + 滑点 + 成本 + 组合归因

**目标**：出来的夏普率不是幻觉。

**关键设计**
- **撮合模型**：可选 VWAP / 开盘 / 收盘价；A 股严格 T+1；涨跌停买不进要模拟。
- **成本模型**：印花税 + 佣金 + 过户费 + 滑点 bps + 冲击成本函数。
- **组合层归因**：不是把单票收益加起来，而是完整持仓 → 因子暴露 / 行业暴露 / 风格暴露归因。
- **未来函数校验**：回测器自身有一层护栏。
- **Walk-forward + Purged CV**：防过拟合，参考量化研究规范。

**对应 Agent**：BacktestAgent（可调用 backtrader / qlib / vectorbt 三个引擎）

---

## D5. 风控层 — Order / Portfolio / Strategy 三级

**目标**：任何决策进入执行前，必过三道闸。

**关键设计**（借鉴 FinRL-X）
- **Order level**：单笔金额上限、单只集中度、频次限制（防止 LLM 抖动导致高频翻单）。
- **Portfolio level**：总仓位上限、行业/风格暴露上限、单日最大回撤触发降仓。
- **Strategy level**：策略级 kill switch、turbulence index / VIX 断路器、异常波动熔断。
- **黑名单**：ST / 退市风险 / 停牌 / 财务造假嫌疑 / 大股东减持强制排除。
- **显式风险清单出报告**：daily_stock_analysis 的经验——LLM 若不强制输出风险，会永远看多。

**对应 Agent**：RiskAgent（三级检查器）+ ComplianceAgent（黑名单 / 合规）

---

## D6. 执行 / 通知层 — 分级发布

**目标**：从"报告可读"到"能真下单"是一条连续谱，按用户信任度分级。

**关键设计**
- **三档执行模式**：dry-run（只出报告） / paper（模拟盘） / live（真实盘，需二次确认）。
- **多通道推送**：企业微信 / 飞书 / Telegram / 邮件 / Discord；决策仪表盘为核心制品。
- **决策仪表盘 schema**：🟢/🟡/🔴 + 评分 + 方向 + 关键买卖点位 + 风险 + 催化 + 操作清单。
- **实盘接口**：Alpaca / IBKR / 券商 API（国内合规风险高，默认仅提示不下单）。

**对应 Agent**：ExecutionAgent + ReportingAgent

---

## D7. 调度 / 编排层 — 交易日历 + 断点续跑

**目标**：能长期无人值守跑，跑挂了不用从头来。

**关键设计**
- **LangGraph 状态机**：每个 Agent 是一个 node，state 持久化到 SQLite。
- **checkpoint 续跑**：任何 node 崩了从最后成功点继续。
- **零成本定时**：GitHub Actions + cron，工作日 18:00 触发。
- **交易日历闸门**：非交易日整个 pipeline 短路，节省 LLM 额度。
- **失败重试与降级**：LLM 超时切 quick 模型；数据源超时切次源。

**对应 Agent**：Orchestrator（不是一个 LLM Agent，而是核心状态机）

---

## D8. 持久化 / 记忆 / 复盘层 — 让决策具备学习闭环

**目标**：这次决策能看到上次结果并反思。这是"多 Agent 团队"vs"多 prompt 拼装"的分水岭。

**关键设计**（借鉴 TradingAgents 的 memory + reflection）
- **决策日志**：每次决策落盘 markdown / JSON，含论据、评级、当时的价格。
- **事后打分**：T+N 日回来算实际收益（原始收益 + alpha vs 基准）。
- **反思生成**：LLM 用"决策 vs 实际结果"生成一段反思，进入下次同标的的 prompt。
- **交叉学习**：跨标的的经验教训也进入 Research Manager 的 system prompt。

**对应 Agent**：MemoryAgent + ReflectionAgent

---

## D9. 可观测性 / 治理层 — 让整个系统可审计

**目标**：任何一个建议都能回溯"为什么这么给"。

**关键设计**
- **全链路 trace**：LangSmith / OpenLLMetry / 自建 SQLite trace 表，每个 Agent 的输入输出全存。
- **成本控制**：每个 Agent 打 tag 记 token & $，日报里显式列出成本。
- **A/B 评估**：分析师阵容、辩论轮数、模型型号都可对照实验。
- **数据版本**：数据快照 hash，回测结果和数据版本绑定。

**对应 Agent**：ObservabilityAgent（非 LLM，横切能力）

---

## 与调研的对照表

| 头部项目 | 我们借鉴的点 | 我们改进的点 |
|---|---|---|
| TradingAgents（93k） | 多角色分析师 + Bull/Bear 辩论 + 决策记忆 + LangGraph checkpoint | 增加 D5 风控三级、D4 组合归因、D2 中国特色因子 |
| Qlib | 因子表达式引擎、PIT 数据库、组合归因 | 用 LLM 做因子生成与解读 |
| FinRL / FinRL-X | 三级风控、Gym env、turbulence 断路器 | 不强绑 RL，作为可插拔策略源 |
| daily_stock_analysis（57k） | 决策仪表盘、多通道推送、GitHub Actions 定时、交易日历闸门 | 从"单 LLM 摘要"升级为"多 Agent 辩论 + 反思" |
| myhhub/stock（13k） | 筹码分布、龙虎榜、K 线形态、多种具名策略 | 作为 FactorAgent / ChipsAgent 的规则库 |
| akshare / adata | 数据源封装 + 多源降级 | 加 Point-in-Time 版本控制 |
| Ghostfolio | 组合追踪 UI、多账户 | 作为可选前端，不做核心 |
| OpenBB | "connect once, consume everywhere"数据平台观 | 数据层参考其抽象 |
