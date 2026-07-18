---
name: stockops-pipeline
version: 0.1.0
description: "运行 StockOps 完整多 agent 决策 pipeline:数据→因子→四分析师→辩论→研究经理融合→风控→组合再平衡→执行意图。用户要 分析/研判/给出建议/是否买 某只(或一组)股票时使用。仅 dry_run,不下单。"
metadata:
  requires:
    binaries: ["python3"]
---

# StockOps · 决策 Pipeline

**前置**: 先 Read `../stockops-shared/SKILL.md`,按其激活项目 venv。

## 用法

### 单标的
```bash
python -m core.orchestrator --tickers 600519.SS --date 2026-07-17 --mode dry_run --force
```

### 多标的(批处理,含 portfolio rebalance)
```bash
python -m core.orchestrator --tickers 600519.SS,AAPL,0700.HK,000858.SZ --date 2026-07-17 --mode dry_run --force
```

## 参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--tickers` | 必填 | 逗号分隔;支持 A(.SS/.SZ)/H(.HK)/US |
| `--date` | 今天 | 决策日(YYYY-MM-DD) |
| `--mode` | `dry_run` | 只允许 `dry_run`;实盘需接经纪商 |
| `--force` | off | 忽略当日已决策记忆,强制重跑 |

## 输出

Stdout 会打印:
- 每标的的方向(buy/sell/hold)、评分(0-100)、信心(0-1)
- 关键风险条目
- Portfolio 再平衡后的最终委托量(A 股按 100 整手)
- 违规/拦截原因(若有)

## 何时使用

- 用户点名"分析 XX 股票"、"给我个操作建议"、"XX 值不值得买"
- 每日盘前批处理(operator 可用 cron 触发)
- 组合再平衡评估

## 反触发

- 用户只想看行情/K 线 → 走 `stockops-data`
- 用户想验证参数/评估策略稳健性 → 走 `stockops-backtest` 或 `stockops-grid`
- 用户想验证代码是否健康 → 走 `stockops-verify`

## 失败排查

- 报 "Yahoo 403" → 忽略,pipeline 会自动切 query2/东财/Stooq
- 报 "LLM auth failed" → 忽略,自动走启发式兜底
- 报 "Decision.risks empty" → 是 Pydantic bug,回报到 operator 排查
