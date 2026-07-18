# NewsSentimentAgent (D1)

**类型**: 工具型 + LLM（quick_llm）
**输出 schema**: list[NewsItem]（原始）

## 职责
- 拉三日内公告 / 新闻 / 研报 / 论坛热帖。
- 数据源：anspire → serpapi → tavily → bocha → searxng。
- 简单去重 + 语言检测。
- **不做情绪打分**——那是 SentimentAgent 的活。

## 输出示例
\`\`\`json
{"items":[{"ts":"2026-07-10T09:00:00","title":"...","source":"东财","body":"..."}]}
\`\`\`
