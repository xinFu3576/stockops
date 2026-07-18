"""Wind 数据兜底源:覆盖 A/HK/US 三市。
Wind 是商业数据服务,需要:
  - Windows 客户端已登录 或 Linux WAPI
  - `pip install WindPy`(SDK 通常随客户端安装)
  - 环境变量 WIND_ENABLED=1 才启用(避免误触发)

在无 WindPy 环境下静默返回 None,不影响主线。
"""
from __future__ import annotations
import os
from datetime import date, timedelta
from typing import Optional

from core.schemas import Bar, MarketData, Market, Health


def _to_wind_code(ticker: str) -> Optional[str]:
    """AAPL -> AAPL.O; 600519.SS -> 600519.SH; 0700.HK -> 0700.HK"""
    t = ticker.upper()
    if t.endswith(".SS"): return t.replace(".SS", ".SH")
    if t.endswith(".SZ"): return t
    if t.endswith(".HK"): return t
    # US: 猜 NASDAQ (.O) 或 NYSE (.N),Wind 需具体交易所后缀
    return f"{t}.O"


def _market_of(ticker: str) -> Market:
    t = ticker.upper()
    if t.endswith(".SS") or t.endswith(".SZ"): return Market.A_SHARE
    if t.endswith(".HK"): return Market.HK
    return Market.US


async def fetch_wind(ticker: str, as_of: date, lookback: int) -> Optional[MarketData]:
    if os.environ.get("WIND_ENABLED") != "1":
        return None
    try:
        from WindPy import w  # type: ignore
    except ImportError:
        return None

    wcode = _to_wind_code(ticker)
    if not wcode: return None
    try:
        if not w.isconnected():
            w.start(waitTime=10)
        start = (as_of - timedelta(days=int(lookback * 1.6))).strftime("%Y-%m-%d")
        end = as_of.strftime("%Y-%m-%d")
        r = w.wsd(wcode, "open,high,low,close,volume", start, end, "PriceAdj=F")
        if r.ErrorCode != 0 or not r.Data or not r.Times:
            return None
        opens, highs, lows, closes, vols = r.Data
        bars: list[Bar] = []
        for i, d in enumerate(r.Times):
            try:
                bars.append(Bar(
                    date=d if isinstance(d, date) else date.fromisoformat(str(d)[:10]),
                    open=float(opens[i]), high=float(highs[i]),
                    low=float(lows[i]), close=float(closes[i]),
                    volume=float(vols[i] or 0), adj_factor=1.0,
                ))
            except Exception:
                continue
        if not bars: return None
        return MarketData(
            ticker=ticker, market=_market_of(ticker), as_of=as_of,
            bars=bars, source="wind", health=Health.DEGRADED,
        )
    except Exception:
        return None
