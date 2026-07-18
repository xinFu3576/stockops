"""D4 参数网格搜索：找最优 _WEIGHTS 组合。

用法：
  python -m tools.grid_search --tickers 600519.SS,AAPL,0700.HK,000858.SZ \
         --date 2026-07-17 --lookback 500 --top 10
"""
from __future__ import annotations
import argparse, asyncio, itertools, math
from datetime import date

import numpy as np
import pandas as pd

from tools.market_data import fetch_market_data
from tools.fundamentals import fetch_fundamentals
from tools.backtest import (
    _factor_matrix, CostModel, _tech_score, _fund_score,
    fundamental_static_score,
)
from core.schemas import MarketData


def _backtest_with_weights(md: MarketData, weights: dict[str, float],
                          fund_static: float = 0.0,
                          sent_static: float = 0.0,
                          macro_static: float = 0.0,
                          allow_short: bool = False) -> dict:
    cost = CostModel(md.market.value if hasattr(md.market, "value") else md.market)

    df = pd.DataFrame([b.model_dump() for b in md.bars]).sort_values("date").reset_index(drop=True)
    fm = _factor_matrix(df)

    tech = fm.apply(_tech_score, axis=1)
    price_fund = fm.apply(_fund_score, axis=1)   # 保留价格代理
    # 混合基本面：50% 价格代理 + 50% F10 常量
    fund = 0.5 * price_fund + 0.5 * fund_static
    sent = pd.Series(sent_static, index=fm.index)
    macro = pd.Series(macro_static, index=fm.index)

    total_w = sum(weights.values()) or 1.0
    score = (tech * weights["technical"] + fund * weights["fundamental"] +
             sent * weights["sentiment"] + macro * weights["macro_event"]) / total_w

    def to_w(s):
        if abs(s) < 0.15: return 0.0
        if s >= 0.55: return 1.0
        if s <= -0.55: return -1.0
        return 0.5 if s > 0 else -0.5

    weights_raw = score.apply(to_w)
    if not allow_short:
        weights_raw = weights_raw.clip(lower=0)
    target_w = weights_raw.shift(1).fillna(0.0)

    buy_leg = target_w.diff().clip(lower=0).fillna(target_w.clip(lower=0))
    sell_leg = (-target_w.diff().clip(upper=0)).fillna(0)
    cost_pct = (buy_leg * cost.buy_cost_bps() + sell_leg * cost.sell_cost_bps()) / 1e4

    ret_close = df["close"].pct_change().fillna(0)
    pnl = target_w.shift(1).fillna(0) * ret_close - cost_pct
    equity = (1 + pnl).cumprod()

    n = len(pnl); td = 252
    ann = float(equity.iloc[-1] ** (td / max(n, 1)) - 1)
    vol = float(pnl.std() * math.sqrt(td))
    sharpe = float((pnl.mean() * td) / vol) if vol > 0 else 0.0
    peak = equity.cummax()
    mdd = float((equity / peak - 1).min())
    bench_ann = float((1 + ret_close).cumprod().iloc[-1] ** (td / max(n, 1)) - 1)
    return {"ann": ann, "sharpe": sharpe, "mdd": mdd,
            "alpha": ann - bench_ann}


def _combos() -> list[dict[str, float]]:
    grid = np.round(np.arange(0.0, 1.01, 0.1), 2)
    out = []
    for a, b, c, d in itertools.product(grid, repeat=4):
        if abs(a + b + c + d - 1.0) < 1e-6:
            out.append({"technical": a, "fundamental": b,
                       "sentiment": c, "macro_event": d})
    return out


async def _prefetch(tickers: list[str], as_of: date, lookback: int):
    mds, funds = [], []
    for t in tickers:
        md = await fetch_market_data(t, as_of, lookback=lookback)
        mds.append(md)
        f = await fetch_fundamentals(t, as_of)
        funds.append(fundamental_static_score(f))
    return mds, funds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--lookback", type=int, default=500)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--objective", choices=["sharpe", "alpha", "ann"], default="sharpe")
    args = ap.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",")]
    as_of = date.fromisoformat(args.date)
    mds, funds = asyncio.run(_prefetch(tickers, as_of, args.lookback))
    print("基本面静态分：")
    for t, f in zip(tickers, funds):
        print(f"  {t:<12} = {f:+.2f}")

    combos = _combos()
    print(f"\n扫描 {len(combos)} 组权重 x {len(tickers)} 标的 ...")

    rows = []
    for w in combos:
        metrics = []
        for md, fs in zip(mds, funds):
            m = _backtest_with_weights(md, w, fund_static=fs)
            metrics.append(m)
        rows.append({
            "w_tech": w["technical"], "w_fund": w["fundamental"],
            "w_sent": w["sentiment"], "w_macro": w["macro_event"],
            "avg_sharpe": round(float(np.mean([m["sharpe"] for m in metrics])), 3),
            "avg_alpha": round(float(np.mean([m["alpha"] for m in metrics])), 4),
            "avg_ann": round(float(np.mean([m["ann"] for m in metrics])), 4),
            "min_sharpe": round(float(np.min([m["sharpe"] for m in metrics])), 3),
        })

    df = pd.DataFrame(rows)
    key = {"sharpe": "avg_sharpe", "alpha": "avg_alpha", "ann": "avg_ann"}[args.objective]
    df = df.sort_values(key, ascending=False)
    print(f"\nTop {args.top} by {args.objective}:")
    print(df.head(args.top).to_string(index=False))

    import os
    os.makedirs("reports", exist_ok=True)
    out = f"reports/grid_search_{args.date}.csv"
    df.to_csv(out, index=False)
    print(f"\n完整结果 -> {out}")


if __name__ == "__main__":
    main()
