---
name: stockops-cron
version: 0.1.0
description: "启动 StockOps 一键日跑 daily.sh(pipeline+verify+reflect+alert),并给出 launchd/crontab 建议。用户说 每天自动跑/定时/盘前预警/schedule 时使用。"
metadata: { requires: { binaries: ["bash","python3"] } }
---
# StockOps · 每日自动化

**前置**: 先 Read `../stockops-shared/SKILL.md`。

## 一键日跑

```bash
"/Users/sendy/Documents/New project/stock-agents-team/daily.sh" 2026-07-17
```

含 3 步: batch_runner(alert) → verify → reflect,全部走 dry_run。

## 定时(推荐 launchd, macOS)

创建 `~/Library/LaunchAgents/com.sendy.stockops.daily.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.sendy.stockops.daily</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>"/Users/sendy/Documents/New project/stock-agents-team/daily.sh" &gt;&gt; ~/Library/Logs/stockops.log 2&gt;&amp;1</string>
  </array>
  <key>StartCalendarInterval</key><array>
    <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
  </array>
</dict></plist>
```

`launchctl load ~/Library/LaunchAgents/com.sendy.stockops.daily.plist` 激活;每周一~周五 18:00 跑。

## OpenClaw heartbeat 替代

也可以给 `stockops_operator` 的 heartbeat.every 设 `4h`,并在心跳指令里显式调用 daily.sh。见 charter。

## 反触发
- 想跑一次:走 stockops-pipeline / stockops-batch,不要装 cron
