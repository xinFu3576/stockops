---
name: stockops-backtest
version: 0.1.0
description: "对指定标的做向量化历史回测(含三档成本模型),输出年化/Sharpe/最大回撤/胜率/alpha/笔数。用户问 策略稳不稳/过去表现/回测多少年/alpha 多少 时使用。"
metadata: { requires: { binaries: ["python3"] } }
---

# StockOps · 回测

**前置**: 先 Read `../stockops-shared/SKILL.md` 并激活 venv。

## 用法

```bash
python -m tools.backtest_cli --tickers 600519.SS,AAPL --date 2026-07-17 --lookback 500
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--tickers` | 必填 | 逗号分隔 |
| `--date` | 今天 | 回测结束日 |
| `--lookback` | 500 | 交易日数量(≈2 年) |
| `--cost` | mid | `low|mid|high` 成本模型 |

## 反触发

- 只想跑一天决策 → `stockops-pipeline`
- 想扫多个权重组合 → `stockops-grid`
