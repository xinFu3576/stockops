# Stock Agents Team

多市场（沪 / 深 / 港 / 美）多 Agent 股票交易研究流水线。
数据、因子、四位分析师、多空辩论、投研经理、回测、风控、执行、复盘全部落地为可运行代码。
LLM + 启发式双通道，无 API key 也能跑；有 key 自动升级到 LLM，一致性校验回退防幻觉。

## 一键跑

```bash
cd stock-agents-team
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# 1) 端到端一次决策 (2026-07-17)
python -m core.orchestrator --tickers 600519.SS,AAPL,0700.HK,000858.SZ \
       --date 2026-07-17 --mode dry_run --force

# 2) 历史回测 (2 年, 向量化, 三档成本)
python -m tools.backtest_cli --tickers 600519.SS,AAPL --date 2026-07-17 --lookback 500

# 3) 参数网格搜索 (找最优 _WEIGHTS)
python -m tools.grid_search --tickers 600519.SS,AAPL,0700.HK,000858.SZ \
       --date 2026-07-17 --top 10 --objective sharpe

# 4) 反思闭环: 给 20 天前的历史决策回填实际收益 + 生成教训
python -m tools.reflect --horizon 20 --as_of 2026-07-17
```

## 9 个设计维度

| 维度 | 代码 | 现状 |
|---|---|---|
| D1 数据 | `tools/market_data.py` + `news.py` + `alt_data.py` + `fundamentals.py` | Yahoo(双主机)+东财+Stooq；东财新闻/公告/龙虎榜/F10；带磁盘缓存 |
| D2 因子 | `tools/factors.py` | 16 技术因子 + 8 财务因子(A 股) + 情绪因子 |
| D3 策略 | `agents_llm/` | 4 分析师 + Bull/Bear 2 轮辩论 + RM 加权融合 |
| D4 回测 | `tools/backtest.py` + `grid_search.py` | 向量化撮合，三档成本，参数网格 |
| D5 风控 | `tools/risk.py` | 订单/组合/策略/合规四级 |
| D6 执行 | `tools/execution.py` | dry_run / paper / live |
| D7 调度 | `core/orchestrator.py` | 并行组 + 交易日闸门 |
| D8 记忆 | `tools/memory.py` + `reflect.py` | JSON 决策日志 + realized_return 回填 + 教训生成 |
| D9 可观测 | `agents_llm/llm_client.py` + `AgentState.trace` | LLM 审计 + 错误 trace |

## LLM 通道 (可选)

复制 `.env.example` 到 `.env`：

```env
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=sk-xxxx
DEEP_LLM=deepseek-chat
QUICK_LLM=deepseek-chat
```

四位分析师 + 辩论 + RM 自动切换到 LLM 通道。校验失败回退到启发式，pipeline 永远能跑通。
**RM 加了一致性 reconcile**：若 LLM 方向与启发式差 ≥ 2 档，强制中性化并降信心 —— 防幻觉。

## 真实数据样本 (as_of=2026-07-17)

### 决策 (启发式无 key)

- **五粮液 000858.SZ** 评分 57 信心 0.48 · fundamental: "毛利率 81.4% 具备护城河 · 净利同比 +82.6% 高增速"
- **茅台 600519.SS** 评分 52 信心 0.39 · sentiment: "舆情 +0.39 覆盖 15 条 涨价/降价"
- **AAPL** 评分 55 信心 0.42 · technical: "MA5/MA20 +5.94% 短期上翘"

### 2 年回测

| 代码 | 年化 | Sharpe | 回撤 | 胜率 | 笔数 | alpha | 基准 |
|---|---|---|---|---|---|---|---|
| 600519.SS | -1.79% | -0.90 | -4.64% | 29% | 7 | +8.01% | -9.79% |
| AAPL | +6.12% | +1.33 | -3.38% | 72% | 25 | -21.22% | +27.34% |
| 0700.HK | -1.16% | -0.15 | -9.39% | 35% | 17 | -21.37% | +20.20% |
| 000858.SZ | -1.25% | -0.35 | -8.02% | 25% | 12 | +21.52% | -22.77% |

策略画像：**趋势跟随+超卖过滤**。熊市 alpha 正（茅台/五粮液），牛市跑输 buy-and-hold（AAPL/腾讯）。

### 网格搜索结果 (avg Sharpe，跨 4 标的)

| w_tech | w_fund | w_sent | w_macro | avg Sharpe | avg alpha |
|---|---|---|---|---|---|
| 0.2 | 0.8 | 0.0 | 0.0 | 0.155 | -2.85% |
| 0.1 | 0.9 | 0.0 | 0.0 | 0.155 | -2.85% |
| 0.3 | 0.7 | 0.0 | 0.0 | 0.135 | -2.53% |

**注**：sentiment / macro 在扫描时 = 0，因为历史 K 线没有对应新闻/龙虎榜快照。当前样本更偏基本面。

## 目录一览

```
core/           数据契约 + 编排
tools/          数据源 / 因子 / 回测 / 风控 / 执行 / 记忆 / 反思 / 网格
agents_llm/     4 分析师 + 辩论 + RM + Trader + Reporting + LLM 客户端
memory/         历史决策 JSON
reports/        回测 / 网格搜索输出
docs/           设计说明
configs/        pipeline 配置
.cache/         数据源磁盘缓存
```

## 下一步建议

1. 把 A 股财务因子加入 grid_search 目标（现在 sentiment/macro 是零向量，扫不到）
2. Trader 引入基于 Kelly 的动态仓位（现在是 5%/10% 固定档）
3. Compliance 层加入 ST/停牌黑名单（东财接口现成）
4. Portfolio 层引入行业相关性约束（现在多标的完全独立）
