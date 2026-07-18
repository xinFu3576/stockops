---
name: stockops-data
version: 0.1.0
description: "读单点数据(K 线/新闻/基本面 F10/龙虎榜/大宗交易/情绪打分),不做决策。用户只问 XX 股票现在多少钱/最近新闻/PE/ROE 时使用。"
metadata: { requires: { binaries: ["python3"] } }
---

# StockOps · 数据查询

**前置**: 先 Read `../stockops-shared/SKILL.md`。

## 单点用法

```bash
# K 线
python -c "from tools.market_data import get_ohlcv; print(get_ohlcv('600519.SS','2025-01-01','2026-07-17').tail())"

# 新闻+情绪
python -c "from tools.news import fetch_news; from tools.sentiment import score_news; xs=fetch_news('600519.SS'); print(score_news(xs))"

# 基本面 F10(只 A 股)
python -c "from tools.fundamentals import fetch_fundamentals; print(fetch_fundamentals('600519.SS'))"

# 龙虎榜/大宗交易
python -c "from tools.alt_data import fetch_lhb; print(fetch_lhb('600519.SS'))"
```

**不要**在这个 skill 里做决策,决策走 `stockops-pipeline`。
