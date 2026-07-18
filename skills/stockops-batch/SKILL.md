---
name: stockops-batch
version: 0.1.0
description: "跑 watchlist 批处理决策 + 预警对比。用户说 跑清单/日报/批处理/预警/watchlist 时使用。"
metadata: { requires: { binaries: ["python3"] } }
---
# StockOps · 批处理 & 预警

**前置**: 先 Read `../stockops-shared/SKILL.md` 并激活 venv。

```bash
# 跑 configs/watchlist.yaml 里的 core 清单
python -m tools.batch_runner --list core --date 2026-07-17
# 或全清单合并
python -m tools.batch_runner --all --date 2026-07-17
```

产物:
- `data/batch_state/batch_YYYY-MM-DD.json` - 当日快照(供次日 diff)
- `reports/alert_YYYY-MM-DD_TS.md` - 人可读日报
- 若配置了 FEISHU_WEBHOOK / SMTP,自动推送(见 stockops-alert)

预警规则(configs/watchlist.yaml):
- `score_delta_threshold`: 与前一存档的评分差绝对值触发阈值
- `confidence_min`: 低于此信心不入 alert
- `risk_block_alert`: 只要风控 block 就 alert
