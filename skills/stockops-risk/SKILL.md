---
name: stockops-risk
version: 0.1.0
description: "单独跑风控/合规/组合模块:检查停牌 ST 黑名单、行业敞口、相关性集群、100 股整手。用户说 检查合规/查停牌/看行业集中度 时使用。"
metadata: { requires: { binaries: ["python3"] } }
---

# StockOps · 风控/合规/组合

**前置**: 先 Read `../stockops-shared/SKILL.md`。

## 合规扫描
```bash
python -c "from tools.compliance import check_compliance; import json; print(json.dumps(check_compliance('600519.SS'),ensure_ascii=False,indent=2))"
```

## 组合再平衡预演
Pipeline 里已经内置。若单独调:
```bash
python -c "from tools.portfolio import Portfolio; from tools import portfolio; portfolio.demo()"
```

## 黑名单文件

`configs/blacklist.txt`,一行一个 ticker。
