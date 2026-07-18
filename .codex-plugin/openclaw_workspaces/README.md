# StockOps Agent Workspaces

1 Operator + 7 Specialists 覆盖 9 维股票交易架构:

| 目录 | Agent | 维度 |
|---|---|---|
| 00_stockops_operator | 交易 Operator | D7 编排 |
| 11_stock_data | 数据/因子 | D1+D2 |
| 12_stock_analyst | 分析师+辩论+RM | D3 |
| 13_stock_backtest | 回测/寻优 | D4 |
| 14_stock_risk | 风控/合规/组合 | D5 |
| 15_stock_execution | 执行(dry_run) | D6 |
| 16_stock_reflection | 复盘/记忆 | D8 |
| 17_stock_observability | 可观测 | D9 |

入口:main → stockops_operator。专家只与 operator 通信。
