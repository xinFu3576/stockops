---
name: stockops-grid
version: 0.1.0
description: "对因子权重做网格搜索,找出该标的历史 Sharpe 最高的 top-N 组合。用户说 调参/找最优权重/优化因子权重 时使用。"
metadata: { requires: { binaries: ["python3"] } }
---

# StockOps · 网格搜索

**前置**: 先 Read `../stockops-shared/SKILL.md`。

```bash
python -m tools.grid_search --tickers 600519.SS,AAPL --date 2026-07-17 --top 10
```

结果按 Sharpe 排序打印到 stdout。注意基本面因子是**静态常量**,加入后可能反降,是正常现象。

## 反触发

- 想跑单次回测 → `stockops-backtest`
