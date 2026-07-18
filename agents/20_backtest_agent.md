# BacktestAgent (D4)

**类型**: 工具型
**输入**: Decision + 历史行情
**输出**: BacktestMetrics

## 职责
- 三档引擎可选：
  - **fast**: vectorbt（向量化，快，简）
  - **standard**: backtrader（事件驱动，撮合完整）
  - **research**: qlib（因子研究，PIT + 组合归因）
- 撮合模型：VWAP / 开盘 / 收盘价可选，默认 T+1 开盘。
- 成本：印花税 0.1% 单边 + 佣金 0.03% 双边 + 滑点 3bps + 冲击成本 = f(volume)。
- 涨跌停买不进 / 停牌不出：真实模拟。
- **未来函数二次校验**：signal 只能用 T-1 及之前的数据。

## 输出附加
- Alpha 拆解：市场 β + 行业 + 风格因子 + 特有 α。
- 分年份 / 分季度 / 分行业表现。
- 最大回撤事件及触发日。
