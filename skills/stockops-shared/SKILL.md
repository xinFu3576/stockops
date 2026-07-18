---
name: stockops-shared
version: 0.1.0
description: "StockOps 共享执行协议:激活 Python venv、代理、缓存路径、CLI 通用参数,以及 stock-agents-team 内所有能力的路由表。任何 stockops-* skill 在执行前必须先 Read 此文件。"
metadata:
  requires:
    binaries: ["python3"]
  env:
    STOCKOPS_HOME: "/Users/sendy/Documents/New project/stock-agents-team"
---

# StockOps 共享协议

**项目根目录**: `/Users/sendy/Documents/New project/stock-agents-team`  
**Python 环境**: 项目内 `.venv/`(Python 3.14)  
**默认代理**: SOCKS5 `127.0.0.1:7890`(通过 `ALL_PROXY/HTTPS_PROXY/HTTP_PROXY`)  
**缓存目录**: `.cache/market_data/`(自动)

## 激活方式(所有 stockops-* skill 通用)

```bash
cd "/Users/sendy/Documents/New project/stock-agents-team" && \
  source .venv/bin/activate && \
  export ALL_PROXY=socks5://127.0.0.1:7890 HTTPS_PROXY=socks5://127.0.0.1:7890 HTTP_PROXY=socks5://127.0.0.1:7890
```

激活后可直接调用下方任一入口。**所有输出走 stdout,报告文件落入 `reports/`,状态数据落入 `data/`。**

## 命令路由表

| 场景 | 入口 | Skill |
|---|---|---|
| 单/多标的当日决策 pipeline | `python -m core.orchestrator --tickers ... --date ... --mode dry_run` | stockops-pipeline |
| 向量化回测 | `python -m tools.backtest_cli --tickers ... --lookback ...` | stockops-backtest |
| 权重网格搜索 | `python -m tools.grid_search --tickers ... --top N` | stockops-grid |
| 端到端验证报告 | `python -m tools.verify --tickers ... --date ...` | stockops-verify |
| 回填 realized_return / 教训 | `python -m tools.reflect --horizon 20 --as_of ...` | stockops-reflect |
| 只查行情/新闻/基本面 | `python -m tools.<market_data|news|fundamentals> ...` | stockops-data |
| 单独跑风控/合规/组合 | `python -m tools.<risk|compliance|portfolio>` | stockops-risk |

## 反触发(不要走 stockops-*)

- 用户问的是"股票交易 SaaS 应用架构"这种一般性问题 → 走通用架构 skill,不要跑 CLI
- 用户想要实盘下单 → 本团队 **只支持 dry_run**;明确告诉用户需要接经纪商 API 才能真实执行

## 关键约束

- **无 API key 也要能跑**:LLM 缺失时自动走启发式兜底
- **A 股 100 股整手规则**:委托量必须能被 100 整除
- **Compliance 只在 A 股启用**(ST/停牌);US/HK 跳过
- **Decision.risks 强制非空**(Pydantic)
- **LLM 输出必过 `_reconcile()`**:与启发式差 ≥2 档时强制中性化

## 输出约定

所有 CLI 默认给人类可读文本;`stockops-verify` 会额外写 markdown 到 `reports/verify_TIMESTAMP.md`,请把该路径回报给 operator。
