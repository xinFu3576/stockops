# Output Contract

Observability 产出:

- 结构化 JSON / YAML 报表(便于 operator 聚合)
- Markdown 文本摘要(供 main 复述)
- 所有产物写到 `outbox/{task_id}/`;不要污染其他 agent 目录

所有决策类产物必须含 `risks[]`(非空);合规类产物必须含 `status: pass|block`。
