# ExecutionAgent (D6)

**类型**: 工具型
**输入**: list[Order] + mode
**输出**: list[Fill]

## mode 分派
- \`dry_run\`: 只记录，不发送，回填模拟 Fill（假设按 Order 价成交）。
- \`paper\`: 走 Alpaca paper / 自建模拟撮合。
- \`live\`: 走券商 API（Alpaca / IBKR / futu / longbridge），**必须触发人工二次确认**。

## live 模式的护栏
- 单日总金额上限（配置）。
- LLM 无法直接切 live，必须 \`--mode=live\` 显式命令行。
- Fill 与 Decision 双向绑定，便于事后归因。
