# AltDataAgent (D1)

**类型**: 工具型
**输出 schema**: AltSignal

## 职责
- **A 股专用**: 龙虎榜 / 大宗交易 / 股东增减持 / 涨停原因。
- **美股专用**: 内幕交易 / 期权 flow / 13F 变动 / FOMC 事件。
- **宏观**: FRED 利率、CPI；A 股社融、M2、北向资金。

## 数据源
- A 股：akshare (\`stock_lhb_stock_detail\`, \`stock_zt_pool_em\` 等)。
- 美股：Finnhub, OpenBB, FRED。
- 事件：Polymarket API（可选）。
