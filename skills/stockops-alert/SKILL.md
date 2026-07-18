---
name: stockops-alert
version: 0.1.0
description: "把 StockOps 报告推送到飞书群或邮箱。用户说 发飞书/推送日报/发到群里/邮件通知 时使用。"
metadata: { requires: { binaries: ["python3"] } }
---
# StockOps · 通知

**前置**: 先 Read `../stockops-shared/SKILL.md`。

环境变量(至少配一路):
- `FEISHU_WEBHOOK` - 飞书自定义机器人 URL
- `FEISHU_SECRET`  - 可选签名密钥
- `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `SMTP_TO` - 邮箱

```bash
python -m tools.notify --title "StockOps 日报" --body-file reports/alert_2026-07-17_XXXX.md
```

未配置时**静默失败**,不阻塞主流程。batch_runner 有 alert 输出时会自动尝试推送。
