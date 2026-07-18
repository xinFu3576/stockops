---
name: stockops-paper
version: 0.1.0
description: "PaperBroker 虚拟撮合:本地纸交易,持久化到 data/paper/。用户说 纸交易/模拟盘/paper mode/看虚拟账户 时使用。"
metadata: { requires: { binaries: ["python3"] } }
---
# StockOps · Paper 撮合

**前置**: 先 Read `../stockops-shared/SKILL.md`。

## 启用 paper 模式

必须显式声明真钱意图开关(paper 也算,防误操作):

```bash
python -m core.orchestrator --tickers 600519.SS --date 2026-07-17 --mode paper \
    --force --i-accept-real-money
```

## 查询虚拟账户

```bash
python -c "import json; print(json.dumps(json.load(open('data/paper/account.json')),indent=2,ensure_ascii=False))"
```

## 重置

```bash
rm -f data/paper/account.json data/paper/ledger.json
# 可选:STOCKOPS_PAPER_CASH=500000 python -m core.orchestrator ...
```

## 反触发
- 想真实下单 → 需接经纪商(IBKR/富途);本插件仅提供 stub
