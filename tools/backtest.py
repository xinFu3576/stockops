"""D4 BacktestAgent — 向量化历史回测

用当前 4-分析师加权规则（与 research_manager 完全一致）在历史 K 线上滚动生成信号，
撮合次日开盘价，计入手续费+滑点+印花税，产出年化/Sharpe/最大回撤/胜率/换手/成本归因。
"""
from __future__ import annotations
import math
from datetime import date
from typing import Callable
import numpy as np
import pandas as pd

from core.schemas import MarketData, Decision, BacktestMetrics


# ============================================================
# 交易成本模型
# ============================================================
class CostModel:
    def __init__(self, market: str):
        self.market = market
        if market in ("SS", "SZ"):
            self.commission = 2.5e-4   # 双边佣金
            self.min_commission = 5.0
            self.stamp_sell = 5e-4     # 印花税，卖出单边
            self.slippage_bps = 5      # 5 bps
        elif market == "HK":
            self.commission = 2.5e-4
            self.min_commission = 30.0
            self.stamp_sell = 1e-3     # 港股印花税双边 0.1%
            self.slippage_bps = 8
        else:  # US
            self.commission = 0.0      # 免佣券商
            self.min_commission = 0.0
            self.stamp_sell = 0.0
            self.slippage_bps = 3

    def buy_cost_bps(self) -> float:
        return self.commission * 1e4 + self.slippage_bps

    def sell_cost_bps(self) -> float:
        return (self.commission + self.stamp_sell) * 1e4 + self.slippage_bps


# ============================================================
# 复用 research_manager 的评分权重（保持一致性）
# ============================================================
_WEIGHTS = {"technical": 0.35, "fundamental": 0.30, "sentiment": 0.15, "macro_event": 0.20}


def _tech_score(row: pd.Series) -> float:
    s = 0.0
    ma_up = row.get("ma5_over_ma20", 0.0)
    ma_slow = row.get("ma20_over_ma60", 0.0)
    if ma_up > 0.02: s += 0.25
    elif ma_up < -0.02: s -= 0.25
    if ma_slow > 0.01: s += 0.15
    elif ma_slow < -0.01: s -= 0.2

    rsi = row.get("rsi_14", 50.0)
    if rsi > 75: s -= 0.15
    elif rsi < 25: s += 0.15

    hist = row.get("macd_hist", 0.0)
    s += 0.1 if hist > 0 else -0.1

    boll = row.get("boll_pos", 0.0)
    if boll > 0.95: s -= 0.1
    elif boll < 0.05: s += 0.1

    pos52 = row.get("pct_of_52w_range", 0.5)
    if pos52 < 0.1: s += 0.1

    vr = row.get("vol_ratio_5_20", 1.0)
    if vr > 1.5 and ma_up > 0: s += 0.1
    elif vr > 1.5 and ma_up < 0: s -= 0.1

    return max(-1.0, min(1.0, s))


def _fund_score(row: pd.Series) -> float:
    ret20 = row.get("ret_20d", 0.0)
    if ret20 > 0.1: return 0.15
    if ret20 < -0.1: return -0.15
    return 0.0




def fundamental_static_score(fund: dict | None) -> float:
    """把 F10 快照映射成 [-1,1] 常量。用于回测期整段做基本面 tilt。"""
    if not fund:
        return 0.0
    s = 0.0
    roe = fund.get("roe_weighted") or 0
    gm = fund.get("gross_margin") or 0
    np_yoy = fund.get("netprofit_yoy") or 0
    rev_yoy = fund.get("revenue_yoy") or 0
    if roe > 15: s += 0.25
    elif roe > 8: s += 0.1
    elif 0 < roe < 5: s -= 0.1
    elif roe <= 0: s -= 0.3
    if gm > 40: s += 0.1
    elif gm and gm < 15: s -= 0.1
    if np_yoy > 30: s += 0.25
    elif np_yoy > 10: s += 0.15
    elif np_yoy < -20: s -= 0.25
    elif np_yoy < 0: s -= 0.1
    if rev_yoy > 20: s += 0.1
    elif rev_yoy < -5: s -= 0.1
    return max(-1.0, min(1.0, s))


def _combine(tech: float, fund: float, sent: float = 0.0, macro: float = 0.0) -> float:
    s = tech * _WEIGHTS["technical"] + fund * _WEIGHTS["fundamental"] +         sent * _WEIGHTS["sentiment"] + macro * _WEIGHTS["macro_event"]
    total_w = sum(_WEIGHTS.values())
    return s / total_w


def _score_to_target_weight(score: float) -> float:
    """[-1,1] score → target position weight [-1,1]. HOLD 附近为 0."""
    if abs(score) < 0.15: return 0.0
    if score >= 0.55: return 1.0
    if score <= -0.55: return -1.0
    if score >= 0.15: return 0.5
    return -0.5


# ============================================================
# 因子矩阵（向量化，比逐日调 compute_factors 快 100 倍）
# ============================================================
def _factor_matrix(df: pd.DataFrame) -> pd.DataFrame:
    c = df["close"].astype(float)
    v = df["volume"].astype(float)
    out = pd.DataFrame(index=df.index)
    out["close"] = c

    ma5 = c.rolling(5).mean()
    ma20 = c.rolling(20).mean()
    ma60 = c.rolling(60).mean()
    out["ma5_over_ma20"] = ma5 / ma20 - 1
    out["ma20_over_ma60"] = ma20 / ma60 - 1

    out["ret_1d"] = c.pct_change(1)
    out["ret_20d"] = c.pct_change(20)

    # RSI
    delta = c.diff()
    up = delta.clip(lower=0).rolling(14).mean()
    dn = (-delta.clip(upper=0)).rolling(14).mean()
    rs = up / dn.replace(0, np.nan)
    out["rsi_14"] = 100 - 100 / (1 + rs)

    # MACD
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    out["macd_hist"] = 2 * (dif - dea)

    # BOLL 位置 [-1,1]
    m20 = c.rolling(20).mean()
    s20 = c.rolling(20).std()
    out["boll_pos"] = (c - m20) / (2 * s20).replace(0, np.nan)

    # 52w
    lo52 = c.rolling(252, min_periods=60).min()
    hi52 = c.rolling(252, min_periods=60).max()
    out["pct_of_52w_range"] = (c - lo52) / (hi52 - lo52).replace(0, np.nan)

    # 量比
    out["vol_ratio_5_20"] = v.rolling(5).mean() / v.rolling(20).mean().replace(0, np.nan)

    # ATR
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    out["atr_14"] = tr.rolling(14).mean()

    return out


# ============================================================
# 回测主体
# ============================================================
def _apply_signal_pipeline(fm: pd.DataFrame) -> pd.Series:
    tech = fm.apply(_tech_score, axis=1)
    fund = fm.apply(_fund_score, axis=1)
    score = tech * _WEIGHTS["technical"] + fund * _WEIGHTS["fundamental"]
    score = score / sum(_WEIGHTS.values())  # 假定 sent/macro=0
    return score.apply(_score_to_target_weight)


def backtest_series(md: MarketData, allow_short: bool = False) -> dict:
    market = md.market.value if hasattr(md.market, "value") else md.market
    cost = CostModel(market)

    df = pd.DataFrame([b.model_dump() for b in md.bars]).sort_values("date").reset_index(drop=True)
    fm = _factor_matrix(df)

    weights_raw = _apply_signal_pipeline(fm)
    if not allow_short:
        weights_raw = weights_raw.clip(lower=0)

    # 信号 T 日收盘生成 → T+1 开盘执行（避免用未来信息）
    target_w = weights_raw.shift(1).fillna(0.0)

    # 用开盘价撮合（无就退回收盘）
    exec_price = df["open"].where(df["open"].notna() & (df["open"] > 0), df["close"]).astype(float)

    # 换手 & 成本
    turnover = target_w.diff().abs().fillna(target_w.abs())
    # 成本 = 单边 turnover * 单边成本 bps；卖出多加印花税
    buy_leg = target_w.diff().clip(lower=0).fillna(target_w.clip(lower=0))
    sell_leg = (-target_w.diff().clip(upper=0)).fillna(0)
    cost_pct = (buy_leg * cost.buy_cost_bps() + sell_leg * cost.sell_cost_bps()) / 1e4

    # 用当日 close 结算持仓（下一日开盘换仓）
    ret_close = df["close"].pct_change().fillna(0)
    # 昨日收盘持仓 * 今日 close/close-1 = 简化，忽略开盘跳空
    pnl = target_w.shift(1).fillna(0) * ret_close - cost_pct
    equity = (1 + pnl).cumprod()

    # 指标
    n = len(pnl)
    trading_days = 252
    total_return = float(equity.iloc[-1] - 1)
    ann = float(equity.iloc[-1] ** (trading_days / max(n, 1)) - 1)
    vol = float(pnl.std() * math.sqrt(trading_days))
    sharpe = float((pnl.mean() * trading_days) / vol) if vol > 0 else 0.0
    peak = equity.cummax()
    dd = (equity / peak - 1).min()
    max_dd = float(dd) if not math.isnan(dd) else 0.0

    # 胜率（按持仓期分段）
    pos = target_w.shift(1).fillna(0)
    entries = (pos != 0) & (pos.shift(1).fillna(0) == 0)
    exits = (pos == 0) & (pos.shift(1).fillna(0) != 0)
    trade_returns: list[float] = []
    in_trade = False
    cur_start = 0
    for i in range(len(pos)):
        if entries.iloc[i] and not in_trade:
            in_trade = True; cur_start = i
        elif exits.iloc[i] and in_trade:
            if i > cur_start:
                seg = equity.iloc[i-1] / equity.iloc[cur_start-1] - 1 if cur_start > 0 else equity.iloc[i-1] - 1
                trade_returns.append(float(seg))
            in_trade = False
    if in_trade and cur_start > 0:
        seg = equity.iloc[-1] / equity.iloc[cur_start-1] - 1
        trade_returns.append(float(seg))
    win_rate = float(np.mean([1 if r > 0 else 0 for r in trade_returns])) if trade_returns else 0.0

    # 基准：买入持有
    bench_ret = (1 + ret_close).cumprod().iloc[-1] - 1
    bench_ann = float((1 + bench_ret) ** (trading_days / max(n, 1)) - 1)
    alpha = ann - bench_ann

    attribution = {
        "gross_return": float((target_w.shift(1) * ret_close).sum()),
        "cost_drag": float(-cost_pct.sum()),
        "avg_turnover_per_day": float(turnover.mean()),
    }

    return {
        "period_start": df["date"].iloc[0],
        "period_end": df["date"].iloc[-1],
        "total_return": total_return,
        "annual_return": ann,
        "annual_vol": vol,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
        "trades": len(trade_returns),
        "turnover": float(turnover.sum()),
        "alpha_vs_benchmark": alpha,
        "benchmark_ann": bench_ann,
        "attribution": attribution,
        "equity_curve": equity.tolist(),
        "dates": [d.isoformat() if hasattr(d, "isoformat") else str(d) for d in df["date"]],
    }


def run_backtest(dec: Decision | None, md: MarketData | None) -> BacktestMetrics | None:
    if md is None:
        return None
    res = backtest_series(md)
    return BacktestMetrics(
        ticker=md.ticker,
        period_start=res["period_start"],
        period_end=res["period_end"],
        total_return=res["total_return"],
        annual_return=res["annual_return"],
        sharpe=res["sharpe"],
        max_drawdown=res["max_drawdown"],
        win_rate=res["win_rate"],
        turnover=res["turnover"],
        alpha_vs_benchmark=res["alpha_vs_benchmark"],
        attribution=res["attribution"],
    )


if __name__ == "__main__":
    import asyncio, json
    from datetime import date as _d
    from tools.market_data import fetch_market_data
    for tk in ("600519.SS", "AAPL", "0700.HK", "000858.SZ"):
        md = asyncio.run(fetch_market_data(tk, _d.today()))
        res = backtest_series(md)
        print(f"{tk:12s}  ann={res['annual_return']:+.2%}  sharpe={res['sharpe']:+.2f}  "
              f"mdd={res['max_drawdown']:.2%}  win={res['win_rate']:.0%}  "
              f"trades={res['trades']}  alpha={res['alpha_vs_benchmark']:+.2%}  "
              f"bench_ann={res['benchmark_ann']:+.2%}")
