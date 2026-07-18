# FactorAgent (D2)

**类型**: 工具型（TA-Lib + pandas）
**输出 schema**: FactorBundle

## 职责
- 计算价量因子：MACD, RSI, KDJ, BOLL, ATR, OBV, CCI, ADX, EMV, PSY, VWMA, Supertrend...
- 计算基本面因子：PE, PB, PS, ROE, 净利同比, 营收同比, FCF yield...
- 计算 K 线形态：60+ candlestick pattern。
- **PIT 校验**: 每个 factor 记录 \`used_data_ts\`，Orchestrator 校验 \`used_data_ts <= as_of\`。
- **IC 提示**: 可选跑一个 30 日滚动 IC，写入 \`ic_hint\`。

## 设计要点
- 内部用因子表达式引擎（简版 qlib），因子用字符串声明：\`"MA(close, 5) / MA(close, 20) - 1"\`。
- 因子分类打 tag，方便 Analyst 按类别取用。
