"""akshare 数据兜底源:A/HK/US 均支持。
仅在其他源均失败或用户显式开启时启用(避免拖慢主线)。

依赖:
  pip install akshare
"""
from __future__ import annotations
from datetime import date, timedelta
from typing import Optional

from core.schemas import Bar, MarketData, Market, Health


def _norm_hist(df, ticker: str, market: Market, as_of: date) -> MarketData:
    bars: list[Bar] = []
    for _, r in df.iterrows():
        try:
            d = r["date"] if "date" in r else r["日期"]
            if hasattr(d, "date"): d = d.date()
            elif isinstance(d, str): d = date.fromisoformat(d[:10])
        except Exception:
            continue
        try:
            bars.append(Bar(
                date=d,
                open=float(r.get("open", r.get("开盘", 0))),
                high=float(r.get("high", r.get("最高", 0))),
                low=float(r.get("low", r.get("最低", 0))),
                close=float(r.get("close", r.get("收盘", 0))),
                volume=float(r.get("volume", r.get("成交量", 0))),
                adj_factor=1.0,
            ))
        except Exception:
            continue
    return MarketData(ticker=ticker, market=market, as_of=as_of,
                      bars=bars, source="akshare", health=Health.DEGRADED)


async def fetch_akshare(ticker: str, as_of: date, lookback: int) -> Optional[MarketData]:
    try:
        import akshare as ak
    except ImportError:
        return None
    start = (as_of - timedelta(days=int(lookback * 1.6))).strftime("%Y%m%d")
    end = as_of.strftime("%Y%m%d")
    t = ticker.upper()
    try:
        if t.endswith(".SS") or t.endswith(".SZ"):
            code = t.split(".")[0]
            df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                    start_date=start, end_date=end, adjust="qfq")
            return _norm_hist(df, ticker, Market.A_SHARE, as_of)
        if t.endswith(".HK"):
            code = t.split(".")[0].zfill(5)
            df = ak.stock_hk_hist(symbol=code, period="daily",
                                  start_date=start, end_date=end, adjust="qfq")
            return _norm_hist(df, ticker, Market.HK, as_of)
        # US
        df = ak.stock_us_daily(symbol=t)
        # 截断到 as_of 之前 lookback 根
        if "date" in df.columns:
            df["date"] = df["date"].astype(str).str.slice(0, 10)
            df = df[df["date"] <= as_of.isoformat()].tail(lookback)
        return _norm_hist(df, ticker, Market.US, as_of)
    except Exception:
        return None
