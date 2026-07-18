# tools/

工具型 Agent 的具体实现放这里。骨架里只暴露函数签名，
真实实现需要接入 akshare / tickflow / yfinance / talib / backtrader 等。

- market_data.py — D1 行情
- news.py — D1 新闻
- alt_data.py — D1 龙虎榜等
- factors.py — D2 因子计算
- sentiment.py — D2 情绪打分（薄封装 LLM）
- chips.py — D2 筹码
- backtest.py — D4
- risk.py — D5
- execution.py — D6
- memory.py — D8
