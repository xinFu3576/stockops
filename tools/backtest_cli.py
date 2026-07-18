"""历史回测 CLI

用法：
  python -m tools.backtest_cli --tickers 600519.SS,AAPL --date 2026-07-17
"""
from __future__ import annotations
import argparse, asyncio
from datetime import date
from tools.market_data import fetch_market_data
from tools.backtest import backtest_series


async def _run(ticker: str, as_of: date, lookback: int) -> dict:
    md = await fetch_market_data(ticker, as_of, lookback=lookback)
    res = backtest_series(md)
    res["ticker"] = ticker
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--lookback", type=int, default=500,
                    help="拉多少个交易日 (默认 500 ≈ 2 年)")
    args = ap.parse_args()
    as_of = date.fromisoformat(args.date)
    tickers = [t.strip() for t in args.tickers.split(",")]

    async def _all():
        return await asyncio.gather(*[_run(t, as_of, args.lookback) for t in tickers])
    results = asyncio.run(_all())

    print(f"{'代码':<12} {'年化':>8} {'Sharpe':>7} {'最大回撤':>9} {'胜率':>6} {'交易':>4} {'alpha':>8} {'基准年化':>9}")
    print("-" * 74)
    for r in results:
        print(f"{r['ticker']:<12} {r['annual_return']:>+7.2%} {r['sharpe']:>+7.2f} "
              f"{r['max_drawdown']:>+8.2%} {r['win_rate']:>5.0%} {r['trades']:>4d} "
              f"{r['alpha_vs_benchmark']:>+7.2%} {r['benchmark_ann']:>+8.2%}")


if __name__ == "__main__":
    main()
