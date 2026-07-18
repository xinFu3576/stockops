"""D2 FactorAgent — 真实版

计算三类因子：
- price_volume: MA/EMA、涨幅、波动、量比、MACD、RSI、KDJ、BOLL 位置、ATR
- chips: 换手率、成交额、量能突破
- fundamental: 骨架（真实项目接财报接口）

所有因子记录 used_data_ts = 用到的最后一个 Bar 日期，Orchestrator 校验 <= as_of。
"""
from __future__ import annotations
from datetime import date
import numpy as np
import pandas as pd

from core.schemas import MarketData, FactorBundle, FactorValue


def _rsi(closes: pd.Series, n: int = 14) -> float:
    delta = closes.diff()
    up = delta.clip(lower=0).rolling(n).mean()
    dn = (-delta.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0


def _macd(closes: pd.Series) -> tuple[float, float, float]:
    ema12 = closes.ewm(span=12, adjust=False).mean()
    ema26 = closes.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    hist = 2 * (dif - dea)
    return float(dif.iloc[-1]), float(dea.iloc[-1]), float(hist.iloc[-1])


def _kdj(df: pd.DataFrame, n: int = 9) -> tuple[float, float, float]:
    low_n = df["low"].rolling(n).min()
    high_n = df["high"].rolling(n).max()
    rsv = 100 * (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan)
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    j = 3 * k - 2 * d
    return float(k.iloc[-1]), float(d.iloc[-1]), float(j.iloc[-1])


def _atr(df: pd.DataFrame, n: int = 14) -> float:
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return float(tr.rolling(n).mean().iloc[-1])


def _boll_position(closes: pd.Series, n: int = 20) -> float:
    """返回 close 在 (mean±2σ) 布林通道内的相对位置：-1 下轨，+1 上轨。"""
    m = closes.rolling(n).mean()
    s = closes.rolling(n).std()
    up = m + 2 * s
    dn = m - 2 * s
    denom = (up - dn).iloc[-1]
    if denom <= 0 or np.isnan(denom):
        return 0.0
    return float((closes.iloc[-1] - m.iloc[-1]) / (2 * s.iloc[-1]))


def compute_factors(md: MarketData | None,
                    fundamentals: dict | None = None) -> FactorBundle | None:
    if md is None or len(md.bars) < 30:
        return None
    df = pd.DataFrame([b.model_dump() for b in md.bars]).sort_values("date").reset_index(drop=True)
    closes = df["close"].astype(float)
    volumes = df["volume"].astype(float)
    last_ts: date = df["date"].iloc[-1]

    factors: list[FactorValue] = []

    def add(name, value, cat):
        try:
            v = float(value)
            if np.isnan(v) or np.isinf(v):
                return
            factors.append(FactorValue(name=name, value=v, category=cat, used_data_ts=last_ts))
        except Exception:
            return

    # ---- 价量因子 ----
    ma5, ma20, ma60 = closes.tail(5).mean(), closes.tail(20).mean(), closes.tail(60).mean()
    add("ma5_over_ma20", ma5 / ma20 - 1, "price_volume")
    add("ma20_over_ma60", ma20 / ma60 - 1, "price_volume")
    add("close_over_ma20", closes.iloc[-1] / ma20 - 1, "price_volume")
    add("ret_1d", closes.iloc[-1] / closes.iloc[-2] - 1, "price_volume")
    add("ret_5d", closes.iloc[-1] / closes.iloc[-6] - 1, "price_volume")
    add("ret_20d", closes.iloc[-1] / closes.iloc[-21] - 1, "price_volume")
    add("vol_20d", closes.pct_change().tail(20).std(), "price_volume")

    dif, dea, hist = _macd(closes)
    add("macd_dif", dif, "price_volume")
    add("macd_hist", hist, "price_volume")
    add("rsi_14", _rsi(closes, 14), "price_volume")

    k, d, j = _kdj(df)
    add("kdj_k", k, "price_volume")
    add("kdj_j", j, "price_volume")

    add("boll_pos", _boll_position(closes), "price_volume")
    add("atr_14", _atr(df), "price_volume")

    # 52 周高低点位置
    hi52 = closes.tail(min(252, len(closes))).max()
    lo52 = closes.tail(min(252, len(closes))).min()
    if hi52 > lo52:
        add("pct_of_52w_range", (closes.iloc[-1] - lo52) / (hi52 - lo52), "price_volume")

    # ---- 筹码 / 量能 ----
    add("vol_ratio_5_20", volumes.tail(5).mean() / max(volumes.tail(20).mean(), 1e-9), "chips")
    if df["turnover"].notna().any():
        add("turnover_mean_5", df["turnover"].tail(5).mean(), "chips")
    if df["amount"].notna().any():
        add("amount_mean_5", float(df["amount"].tail(5).mean()), "chips")

    # ---- 基本面 ----
    if fundamentals:
        for k, v in fundamentals.items():
            if isinstance(v, (int, float)) and k not in ("as_of",):
                add(f"fund_{k}", v, "fundamental")

    return FactorBundle(ticker=md.ticker, as_of=md.as_of, factors=factors, pit_verified=True)


if __name__ == "__main__":
    import asyncio
    from datetime import date as _d
    from tools.market_data import fetch_market_data
    md = asyncio.run(fetch_market_data("600519.SS", _d.today()))
    fb = compute_factors(md)
    print("bars", len(md.bars), "factors", len(fb.factors))
    for f in fb.factors:
        print(f"  {f.name:22s} = {f.value:+.4f}  ({f.category})")
