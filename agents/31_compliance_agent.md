# ComplianceAgent (D5)

**类型**: 规则（无 LLM）
**输入**: Decision + 静态黑名单 / 上市状态表
**输出**: RiskCheckResult(level="compliance")

## 检查项
- ST / *ST / 退市风险警示 → block
- 停牌 → block
- 财报被出具"非标"意见 → block
- 上市不满 1 年 → warn（不 block，但提示）
- 大股东减持公告 24h 内 → warn
- 用户自定义黑名单 → block
