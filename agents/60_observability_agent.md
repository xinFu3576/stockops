# ObservabilityAgent (D9)

**类型**: 横切工具（非 LLM）
**输入**: 所有 Agent 的事件
**输出**: trace / cost / 报警

## 存储
- \`memory/traces.sqlite\`：node_name, ticker, ts, input_hash, output_hash, tokens, cost, latency, status。

## 输出
- 每次跑批产出一份 \`reports/{date}_run.json\`：
  - 每 Agent 调用次数 / token / $
  - 每 ticker 端到端成本
  - 失败节点 & 降级次数
- 每周汇总，超预算报警。

## A/B 支持
- 支持 \`--variant=v1|v2\`，不同 variant 结果分开存，便于对照。
