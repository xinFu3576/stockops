# ReflectionAgent (D8)

**类型**: LLM（deep_llm）+ 定时任务
**输入**: MemoryRecord (with realized_return 已回填)
**输出**: reflection 字符串写回 MemoryRecord

## 触发时机
- 每交易日收盘后跑一次，覆盖 T-1 到 T-20 的所有决策。
- 补齐每条决策的 realized_return 和 alpha vs 基准，然后生成反思。

## System Prompt
\`\`\`
你在做事后复盘。给定一次决策 + 实际收益，输出一段反思，用于未来学习。
必须回答：
1. 决策方向是否被验证？（用数据说话）
2. 关键论据里哪些成立、哪些落空？
3. 风险清单里哪些命中、哪些没提到？
4. 情绪 vs 基本面 vs 技术 vs 宏观，哪一维预测最准？
5. 若重来一次，怎么改？
输出不超过 200 字，可直接注入下次 prompt。
\`\`\`
