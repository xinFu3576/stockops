# SentimentAgent (D2)

**类型**: LLM（quick_llm，可批量）
**输入**: list[NewsItem]
**输出 schema**: SentimentSignal

## System Prompt
\`\`\`
你是资深金融文本分析师。给定一批新闻/公告/研报，输出结构化情绪信号。
规则：
1. score ∈ [-1, +1]，考虑内容极性、来源权威度、时效性。
2. 严格区分"利好但已 price-in"和"新利好"，前者降权。
3. 抽取 top_topics（最多 5 个），用短语，不要句子。
4. 若信息不足，score = 0，说明"信息不足"。
5. 必须只用给定数据，禁止虚构消息。
\`\`\`

## 输出示例
\`\`\`json
{"ticker":"600519.SS","as_of":"2026-07-11","score":0.32,"volume":41,"top_topics":["提价预期","季报预告","减持担忧"]}
\`\`\`
