# MarketDataAgent (D1)

**类型**: 工具型（无 LLM）
**输出 schema**: MarketData

## 职责
- 拉 OHLCV + 复权因子 + 停复牌标记 + ST 状态。
- **多源降级**: tickflow → akshare → baostock → yfinance。
- 关键守卫：
  - Point-in-Time: 只返回 \`as_of\` 及之前的数据。
  - 除权除息前复权：默认返回后复权，保留原始价用于展示。
  - 停牌日不算 volume=0，标记 halted=True。

## 工具接口
\`\`\`python
def fetch(ticker: str, as_of: date, lookback_days: int = 250) -> MarketData: ...
\`\`\`

## 常见坑
- yfinance 对 A 股偶尔漏数据，必须交叉校验。
- akshare 部分接口不返回复权因子，需要单独拉。
