"""生成一份自动化验证报告，供部署前 sanity check。

用法：
  python -m tools.verify --tickers 600519.SS,AAPL,0700.HK,000858.SZ --date 2026-07-17
"""
from __future__ import annotations
import argparse, asyncio, json, os, sys
from datetime import date, datetime

from core.orchestrator import run_batch
from tools.backtest import backtest_series
from tools.market_data import fetch_market_data


async def _one_backtest(t, as_of, lookback=500):
    md = await fetch_market_data(t, as_of, lookback=lookback)
    return t, backtest_series(md)


async def main_async(tickers: list[str], as_of: date, out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")

    lines: list[str] = []
    lines.append(f"# 部署前验证报告 · {ts}")
    lines.append(f"标的: {', '.join(tickers)}")
    lines.append(f"日期: {as_of}")
    lines.append("")

    # 1) Live pipeline
    lines.append("## 1. 端到端 pipeline")
    result = await run_batch(tickers, as_of, mode="dry_run", force=True)
    for st in result["states"]:
        d = st.decision
        if d is None:
            lines.append(f"- **{st.ticker}** — 无决策 (trace: {st.trace})")
            continue
        lines.append(f"- **{st.ticker}** 方向={d.direction.value} 评分={d.score} 信心={d.confidence:.2f}")
    if result["violations"]:
        lines.append("")
        lines.append("### 组合层违规")
        for v in result["violations"]:
            lines.append(f"- {v}")
    lines.append("")

    # 2) Backtest
    lines.append("## 2. 2 年回测 (含成本)")
    lines.append("| 代码 | 年化 | Sharpe | 回撤 | 胜率 | 笔数 | alpha | 基准年化 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for t in tickers:
        _, r = await _one_backtest(t, as_of)
        lines.append(
            f"| {t} | {r['annual_return']:+.2%} | {r['sharpe']:+.2f} | "
            f"{r['max_drawdown']:+.2%} | {r['win_rate']:.0%} | {r['trades']} | "
            f"{r['alpha_vs_benchmark']:+.2%} | {r['benchmark_ann']:+.2%} |"
        )
    lines.append("")

    # 3) Sanity checks
    lines.append("## 3. Sanity Checks")
    checks = []
    checks.append(("数据源可达", any(st.market_data for st in result["states"])))
    checks.append(("四位分析师全部产出", all(len(st.verdicts) == 4 for st in result["states"])))
    checks.append(("辩论至少 4 轮", all(len(st.debate) >= 4 for st in result["states"])))
    checks.append(("每个 Decision.risks ≥ 1", all(st.decision is None or len(st.decision.risks) >= 1 for st in result["states"])))
    checks.append(("风控无异常 block (非停牌)", all(st.risk is None or st.risk.final_action != "block" for st in result["states"])))
    for label, ok in checks:
        lines.append(f"- {'✅' if ok else '❌'} {label}")
    lines.append("")

    # 4) File integrity
    lines.append("## 4. 模块清单")
    files_expected = [
        "core/schemas.py", "core/orchestrator.py",
        "tools/market_data.py", "tools/news.py", "tools/sentiment.py",
        "tools/alt_data.py", "tools/fundamentals.py", "tools/factors.py",
        "tools/backtest.py", "tools/grid_search.py", "tools/risk.py",
        "tools/compliance.py", "tools/portfolio.py",
        "tools/execution.py", "tools/memory.py", "tools/reflect.py",
        "agents_llm/analysts.py", "agents_llm/debate.py",
        "agents_llm/research_manager.py", "agents_llm/trader.py",
        "agents_llm/reporting.py", "agents_llm/llm_client.py",
    ]
    for fn in files_expected:
        ok = os.path.exists(fn)
        lines.append(f"- {'✅' if ok else '❌'} {fn}")

    report_path = os.path.join(out_dir, f"verify_{ts}.md")
    with open(report_path, "w") as fh:
        fh.write("\n".join(lines))
    print(f"报告写入 -> {report_path}")
    print("\n" + "\n".join(lines[:40]))

    # 全部通过则退出 0
    all_ok = all(ok for _, ok in checks)
    sys.exit(0 if all_ok else 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--out", default="reports")
    args = ap.parse_args()
    tickers = [t.strip() for t in args.tickers.split(",")]
    as_of = date.fromisoformat(args.date)
    asyncio.run(main_async(tickers, as_of, args.out))


if __name__ == "__main__":
    main()
