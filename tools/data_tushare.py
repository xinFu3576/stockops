"""tushare pro 兜底(仅 A 股):需 TUSHARE_TOKEN。
免费额度足够覆盖 EPS/PE/PB 等基本面。
"""
from __future__ import annotations
import os
from datetime import date, timedelta
from typing import Optional

from core.schemas import Bar, MarketData, Market, Health


async def fetch_tushare(ticker: str, as_of: date, lookback: int) -> Optional[MarketData]:
    token = os.environ.get("TUSHARE_TOKEN")
    if not token: return None
    try:
        import tushare as ts
    except ImportError:
        return None
    if not (ticker.upper().endswith(".SS") or ticker.upper().endswith(".SZ")):
        return None
    code = ticker.upper().split(".")[0]
    suffix = "SH" if ticker.upper().endswith(".SS") else "SZ"
    ts_code = f"{code}.{suffix}"
    try:
        ts.set_token(token)
        pro = ts.pro_api()
        start = (as_of - timedelta(days=int(lookback * 1.6))).strftime("%Y%m%d")
        end = as_of.strftime("%Y%m%d")
        df = pro.daily(ts_code=ts_code, start_date=start, end_date=end)
        df = df.sort_values("trade_date")
        bars: list[Bar] = []
        for _, r in df.iterrows():
            d = date(int(r["trade_date"][:4]), int(r["trade_date"][4:6]), int(r["trade_date"][6:8]))
            bars.append(Bar(date=d, open=float(r["open"]), high=float(r["high"]),
                            low=float(r["low"]), close=float(r["close"]),
                            volume=float(r["vol"]) * 100, adj_factor=1.0))  # 手→股
        return MarketData(ticker=ticker, market=Market.A_SHARE, as_of=as_of,
                          bars=bars, source="tushare", health=Health.DEGRADED)
    except Exception:
        return None
