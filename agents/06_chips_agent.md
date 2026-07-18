# ChipsAgent (D2 · A 股特色)

**类型**: 工具型
**输出 schema**: FactorBundle (category="chips")

## 职责
- **筹码分布**（Position Cost Distribution）：210 日均线，与东财口径一致。
- **主力资金流向**：超大单/大单/中单/小单净额。
- **机构持股集中度变化**。
- **龙虎榜净买入**（复用 AltDataAgent 数据）。
- **涨停原因**：涨停连板数、开板次数、封单金额。

## 为什么值得单独设一个 Agent
- 这些因子是中国市场特有，海外框架（qlib 外）几乎不做。
- 短线策略（stock-scanner, myhhub, KHunter）都重度依赖这些因子。
