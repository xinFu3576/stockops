---
name: stockops-dashboard
version: 0.1.0
description: "启动 StockOps 零依赖 Web 仪表盘 http://127.0.0.1:8765/。用户说 打开仪表盘/看看团队现在什么状态/给我个 UI 时使用。"
metadata: { requires: { binaries: ["python3"] } }
---
# StockOps · 仪表盘

**前置**: 先 Read `../stockops-shared/SKILL.md`。

```bash
python -m dashboard.server              # 8765
python -m dashboard.server --port 9000
```

功能:
- 项目状态 / 权重 / paper 账户 / 最近报告
- 一键决策 / 回测 / 健康检查 / 学习 / 清 paper
- 15 秒自动刷新
- **零外部依赖**(仅标准库),不需要 pip 装 streamlit

反触发:
- 想跑单条命令 → 用 manage.py / 各 stockops-* skill 的 CLI
