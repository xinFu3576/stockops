# Input Contract

Task Packet 必须含: task_id, owner_agent, objective, deliverables[]。
常见字段: tickers, date/as_of, lookback, mode(dry_run), context。

字段缺失 → 回 INVALID_TASK_PACKET。
