# ReportingAgent (D6)

**类型**: LLM（quick_llm）+ 模板
**输入**: 整个 AgentState
**输出**: 决策仪表盘 markdown + 多通道推送

## 决策仪表盘模板（借鉴 daily_stock_analysis）
\`\`\`
🎯 {as_of} 决策仪表盘
共分析 {N} 只 | 🟢买入:X 🟡观望:Y 🔴卖出:Z

📊 分析结果摘要
🟢 {name}({code}): {direction_cn} | 评分 {score} | {trend}
...

## {name} ({code})
📰 重要信息速览
💭 舆情情绪: {sentiment_summary}
📊 业绩预期: {fundamental_summary}

🚨 风险警报:
- {risk_1}
- {risk_2}
- {risk_3}

✨ 利好催化:
- {catalyst_1}
- {catalyst_2}

📢 最新动态: {latest_news}

✅ 操作检查清单:
- {checklist_1}
- {checklist_2}

💡 参考位: 买入 {entry} / 止损 {stop} / 止盈 {tp}
⏱ 时间视角: {horizon} 天
\`\`\`

## 多通道
- 企业微信 / 飞书 markdown 卡片
- Telegram HTML
- 邮件（含完整 markdown 附件）
