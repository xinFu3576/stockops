"""D1 MarketDataAgent — 真实实现

主源  : Yahoo Finance chart API (免 key, 境外 CDN, 稳定)
备源 1: 东方财富 push2his (国内, 与东财口径一致)
备源 2: Stooq CSV

ticker 规范:
  A 股: 6xxxxx.SS / 6xxxxx.SH / 000xxx.SZ / 3xxxxx.SZ
  港股: 0700.HK
  美股: AAPL / NVDA

Yahoo 符号自动转换:
  .SS -> .SS ; .SH -> .SS ; .SZ -> .SZ ; .HK 补零到 4 位 -> 0700.HK
"""
from __future__ import annotations
import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any
import httpx

from core.schemas import MarketData, Bar, Market, Health


import random
UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 Chrome/125 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
]
def _ua() -> str:
    return random.choice(UAS)


def _client(direct: bool = False) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(20.0, connect=10.0),
        headers={
            "User-Agent": _ua(),
            "Accept": "application/json, text/plain, */*",
            "Connection": "close",
        },
        trust_env=not direct,
        http2=False,
    )


async def _get(url: str, params: dict | None = None, retries: int = 3,
               direct_first: bool = False) -> httpx.Response:
    last: Exception | None = None
    orders = (True, False) if direct_first else (False, True)
    for use_direct in orders:
        for i in range(retries):
            try:
                async with _client(direct=use_direct) as cli:
                    r = await cli.get(url, params=params)
                    r.raise_for_status()
                    return r
            except Exception as e:
                last = e
                await asyncio.sleep(0.3 * (i + 1))
    raise last or RuntimeError("http failed")


def _classify(ticker: str) -> tuple[Market, str, str, str]:
    """返回 (Market, 东财 secid, 显示代码, yahoo 符号)。"""
    t = ticker.upper()
    if t.endswith(".SS") or t.endswith(".SH"):
        code = t.split(".")[0]
        return Market.A_SS, f"1.{code}", code, f"{code}.SS"
    if t.endswith(".SZ"):
        code = t.split(".")[0]
        return Market.A_SZ, f"0.{code}", code, f"{code}.SZ"
    if t.endswith(".HK"):
        code = t.split(".")[0].zfill(4)
        return Market.HK, f"116.{code.zfill(5)}", code, f"{code}.HK"
    return Market.US, f"105.{t}", t, t


# ---------- Yahoo ----------
async def _yahoo(yahoo_sym: str, as_of: date, lookback: int) -> list[Bar]:
    end = int(datetime(as_of.year, as_of.month, as_of.day,
                       tzinfo=timezone.utc).timestamp()) + 86400
    start = end - lookback * 2 * 86400
    params = {"period1": start, "period2": end, "interval": "1d",
              "includePrePost": "false", "events": "div,splits"}
    r = None
    last_err = None
    for h in ("query2.finance.yahoo.com", "query1.finance.yahoo.com"):
        try:
            r = await _get(f"https://{h}/v8/finance/chart/{yahoo_sym}", params=params)
            break
        except Exception as e:
            last_err = e
            await asyncio.sleep(0.4)
    if r is None:
        raise last_err or RuntimeError("yahoo all hosts failed")
    js = r.json()
    result = ((js.get("chart") or {}).get("result") or [])
    if not result:
        return []
    ind = result[0]
    ts = ind.get("timestamp") or []
    q = ((ind.get("indicators") or {}).get("quote") or [{}])[0]
    adj_close = (((ind.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose") or []
    opens = q.get("open") or []
    highs = q.get("high") or []
    lows = q.get("low") or []
    closes = q.get("close") or []
    vols = q.get("volume") or []
    bars: list[Bar] = []
    for i, sec in enumerate(ts):
        try:
            d = datetime.fromtimestamp(sec, tz=timezone.utc).date()
            if d > as_of or closes[i] is None:
                continue
            adj_factor = 1.0
            if i < len(adj_close) and adj_close[i] and closes[i]:
                adj_factor = float(adj_close[i]) / float(closes[i])
            bars.append(Bar(
                date=d, open=float(opens[i]), high=float(highs[i]),
                low=float(lows[i]), close=float(closes[i]),
                volume=float(vols[i] or 0),
                adj_factor=adj_factor,
            ))
        except Exception:
            continue
    return bars


# ---------- 东方财富 ----------
async def _eastmoney(secid: str, as_of: date, lookback: int) -> list[Bar]:
    end = as_of.strftime("%Y%m%d")
    start = (as_of - timedelta(days=lookback * 2)).strftime("%Y%m%d")
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid, "klt": 101, "fqt": 1,
        "beg": start, "end": end,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "_": "0",
    }
    r = await _get(url, params=params, retries=3, direct_first=False)
    js = r.json()
    klines = (js.get("data") or {}).get("klines") or []
    bars: list[Bar] = []
    for line in klines:
        parts = line.split(",")
        d = date.fromisoformat(parts[0])
        if d > as_of:
            continue
        bars.append(Bar(
            date=d,
            open=float(parts[1]), close=float(parts[2]),
            high=float(parts[3]), low=float(parts[4]),
            volume=float(parts[5]),
            amount=float(parts[6]) if parts[6] else None,
            turnover=float(parts[10]) if len(parts) > 10 and parts[10] else None,
        ))
    return bars


# ---------- Stooq ----------
async def _stooq(ticker: str, as_of: date, lookback: int) -> list[Bar]:
    sym = ticker.lower()
    if sym.endswith(".ss") or sym.endswith(".sh"):
        sym = sym.split(".")[0] + ".sh"
    elif sym.endswith(".sz"):
        sym = sym.split(".")[0] + ".sz"
    elif sym.endswith(".hk"):
        sym = sym.split(".")[0].zfill(4) + ".hk"
    else:
        sym = sym + ".us"
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
    r = await _get(url, retries=2)
    text = r.text
    lines = text.strip().splitlines()
    if len(lines) < 2 or "Date" not in lines[0]:
        return []
    bars: list[Bar] = []
    for line in lines[1:]:
        try:
            d, o, h, l, c, v = line.split(",")
            dd = date.fromisoformat(d)
            if dd > as_of:
                continue
            bars.append(Bar(date=dd, open=float(o), high=float(h), low=float(l),
                            close=float(c), volume=float(v or 0)))
        except Exception:
            continue
    return bars[-lookback:]



# ---------- 磁盘缓存 (per-ticker × as_of × lookback) ----------
import json, os
_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".cache", "market_data")


def _cache_key(ticker: str, as_of, lookback: int) -> str:
    safe = ticker.replace("/", "_")
    return os.path.join(_CACHE_DIR, f"{safe}_{as_of}_{lookback}.json")


def _cache_load(ticker: str, as_of, lookback: int) -> MarketData | None:
    fp = _cache_key(ticker, as_of, lookback)
    if not os.path.exists(fp):
        return None
    try:
        with open(fp) as fh:
            return MarketData.model_validate_json(fh.read())
    except Exception:
        return None


def _cache_save(md: MarketData, lookback: int) -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)
    fp = _cache_key(md.ticker, md.as_of, lookback)
    try:
        with open(fp, "w") as fh:
            fh.write(md.model_dump_json())
    except Exception:
        pass


# ---------- 门面 ----------
async def fetch_market_data(ticker: str, as_of: date, lookback: int = 250,
                             use_cache: bool = True) -> MarketData:
    if use_cache:
        c = _cache_load(ticker, as_of, lookback)
        if c is not None:
            return c
    market, secid, _code, yahoo_sym = _classify(ticker)
    errs: list[str] = []

    for src_name, fn in (
        ("yahoo", lambda: _yahoo(yahoo_sym, as_of, lookback)),
        ("eastmoney", lambda: _eastmoney(secid, as_of, lookback)),
        ("stooq", lambda: _stooq(ticker, as_of, lookback)),
    ):
        try:
            bars = await fn()
            if len(bars) >= 20:
                health = Health.OK if src_name == "yahoo" else Health.DEGRADED
                md = MarketData(ticker=ticker, market=market, as_of=as_of,
                                bars=bars, source=src_name, health=health)
                _cache_save(md, lookback)
                return md
            errs.append(f"{src_name}: only {len(bars)} bars")
        except Exception as e:
            errs.append(f"{src_name}: {type(e).__name__}: {e}")

    # -- 兜底源(可选依赖) --
    try:
        from tools.data_akshare import fetch_akshare
        md = await fetch_akshare(ticker, as_of, lookback)
        if md and len(md.bars) >= 20:
            _cache_save(md, lookback)
            return md
        if md: errs.append(f"akshare: only {len(md.bars)} bars")
    except Exception as e:
        errs.append(f"akshare: {type(e).__name__}: {e}")

    try:
        from tools.data_tushare import fetch_tushare
        md = await fetch_tushare(ticker, as_of, lookback)
        if md and len(md.bars) >= 20:
            _cache_save(md, lookback)
            return md
        if md: errs.append(f"tushare: only {len(md.bars)} bars")
    except Exception as e:
        errs.append(f"tushare: {type(e).__name__}: {e}")


    try:
        from tools.data_wind import fetch_wind
        md = await fetch_wind(ticker, as_of, lookback)
        if md and len(md.bars) >= 20:
            _cache_save(md, lookback)
            return md
        if md: errs.append(f"wind: only {len(md.bars)} bars")
    except Exception as e:
        errs.append(f"wind: {type(e).__name__}: {e}")

    raise RuntimeError(f"all sources failed for {ticker}: " + " | ".join(errs))
    # unreachable


if __name__ == "__main__":
    from datetime import date as _d
    async def _demo():
        for tk in ("600519.SS", "AAPL", "0700.HK", "000858.SZ"):
            try:
                md = await fetch_market_data(tk, _d.today())
                print(f"{tk:12s} -> {md.source:10s} bars={len(md.bars)} last={md.bars[-1].date} close={md.bars[-1].close}")
            except Exception as e:
                print(f"{tk:12s} -> FAIL {e}")
    asyncio.run(_demo())
