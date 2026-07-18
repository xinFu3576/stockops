---
name: stockops-watch
version: 0.1.0
description: "分钟级实时价格预警(可循环)。用户说 盯盘/分钟/实时价格/涨跌超过 X 提醒 时使用。"
metadata: { requires: { binaries: ["python3"] } }
---
# StockOps · 实时预警

**前置**: 先 Read `../stockops-shared/SKILL.md`。

```bash
# 60 秒轮询,变动 3% 触发
python -m tools.price_watch --list core --pct 3 --interval 60

# 只跑一次快照
python -m tools.price_watch --list core --once
```

- A 股走新浪 hq.sinajs.cn(需 Referer,已内置)
- H 股走同源
- US 走项目 market_data._yahoo(经 SOCKS5)
- 若有 FEISHU_WEBHOOK / SMTP_*,自动推送

数据落盘 `data/price_watch/last.json`。
