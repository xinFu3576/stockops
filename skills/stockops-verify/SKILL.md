---
name: stockops-verify
version: 0.1.0
description: "端到端健康检查:跑 pipeline+回测+4 项 sanity check,生成 markdown 报告到 reports/。用户说 检查团队健康/端到端验证/deploy 前检查 时使用。"
metadata: { requires: { binaries: ["python3"] } }
---

# StockOps · 部署前验证

**前置**: 先 Read `../stockops-shared/SKILL.md`。

```bash
python -m tools.verify --tickers 600519.SS,AAPL,0700.HK,000858.SZ --date 2026-07-17
```

报告落到 `reports/verify_YYYYMMDD-HHMMSS.md`,operator 应把该路径原样上报给 main。

Sanity checks:
- 数据源可达
- 4 位分析师全部产出
- 辩论 ≥4 轮
- Decision.risks 非空
- 风控无异常 block
