# RiskAgent (D5)

**类型**: 规则 + LLM 补充解释
**输入**: Decision + 当前 portfolio 快照 + 市场状态
**输出**: RiskReport

## 三级检查

### Order level
- 单笔金额 ≤ 账户 5%（可配置）
- 24h 内同一标的翻单次数 ≤ 2（防 LLM 抖动）
- 逆势加仓禁令（已亏损 -8% 禁止加仓）

### Portfolio level
- 单只集中度 ≤ 15%
- 单行业集中度 ≤ 30%
- 总仓位上限（regime-adaptive）：risk_on ≤ 90% / neutral ≤ 70% / risk_off ≤ 40%
- 日内回撤 > 3% 触发降仓 50%

### Strategy level
- **Turbulence index**（借鉴 FinRL）> 阈值触发全策略停手
- VIX > 30 降仓
- 策略级 kill switch（人工可关闭）

## LLM 参与点
- 若规则给出 downsize，LLM 生成 "为什么降 & 降到多少" 的解释。
- 若规则冲突（Order pass 但 Strategy block），LLM 汇总解释。
