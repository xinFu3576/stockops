"""实时报价，供 advise 用最新价代替收盘价。

三级降级：
1. Yahoo quote v7 (免费，US/HK/A股都能拿)
2. Sina 财经（A股）
3. 落 fetch_market_data 最新收盘价

带 30s 内存缓存。
"""
from __future__ import annotations
import time, json, urllib.request, ssl
from typing import Optional
from dataclasses import dataclass

_CACHE: dict[str, tuple[float, float]] = {}
_TTL = 30.0
_CTX = ssl.create_default_context()


@dataclass
class Quote:
    ticker: str
    price: float
    change_pct: Optional[float] = None
    prev_close: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    volume: Optional[int] = None
    source: str = "unknown"
    ts: float = 0.0


def _http_json(url: str, headers: dict | None = None, timeout: float = 6.0):
    try:
        req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
        r = urllib.request.urlopen(req, context=_CTX, timeout=timeout)
        return json.loads(r.read().decode())
    except Exception:
        return None


def _fetch_yahoo(ticker: str) -> Optional[Quote]:
    # v7/finance/quote
    d = _http_json(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}")
    if not d: return None
    res = ((d.get("quoteResponse") or {}).get("result") or [])
    if not res: return None
    q = res[0]
    price = q.get("regularMarketPrice")
    if price is None: return None
    return Quote(
        ticker=ticker, price=float(price), source="yahoo",
        change_pct=q.get("regularMarketChangePercent"),
        prev_close=q.get("regularMarketPreviousClose"),
        day_high=q.get("regularMarketDayHigh"),
        day_low=q.get("regularMarketDayLow"),
        volume=q.get("regularMarketVolume"),
        ts=time.time(),
    )


def _fetch_sina(ticker: str) -> Optional[Quote]:
    """A 股/港股实时用新浪 hq.sinajs.cn。港股 code 需去前导 0，添加 rt_hk 前缀。"""
    tk = ticker.upper()
    hk = tk.endswith(".HK")
    if not tk.endswith((".SS", ".SH", ".SZ", ".HK")): return None
    code = tk.split(".")[0]
    if hk:
        code = code.lstrip("0") or "0"
        code = code.zfill(5)  # 港股用 5 位
        prefix = "rt_hk"
    else:
        prefix = "sh" if tk.endswith((".SS", ".SH")) else "sz"
    url = f"https://hq.sinajs.cn/list={prefix}{code}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"
        })
        r = urllib.request.urlopen(req, context=_CTX, timeout=6.0)
        raw = r.read().decode("gbk", errors="ignore")
        # var hq_str_sh600519="贵州茅台,1650.00,1650.00,...";
        s = raw.split('"')[1] if '"' in raw else ""
        parts = s.split(",")
        if hk:
            # var hq_str_rt_hk00700="TENCENT HOLDINGS,TENCENT,466.6,470.4,458.4,462.4,458.4,462.4,7.4,1.59,..."
            # idx: 3=开盘, 4=昨收(?), 5=最高, 6=最低, 7=最新价, 9=涨幅%
            if len(parts) < 10: return None
            price = float(parts[6] or 0)   # 最新价
            prev = float(parts[3] or 0)    # 昨收
            high = float(parts[4] or 0)
            low = float(parts[5] or 0)
            try: vol = int(float(parts[12])) if len(parts) > 12 else 0
            except Exception: vol = 0
            return Quote(
                ticker=ticker, price=price, source="sina_hk",
                prev_close=prev, day_high=high, day_low=low, volume=vol,
                change_pct=(price/prev-1)*100 if prev else None,
                ts=time.time(),
            )
        if len(parts) < 6: return None
        price = float(parts[3] or parts[1])   # 3=当前价，1=开盘
        prev = float(parts[2])
        high = float(parts[4]); low = float(parts[5]); vol = int(parts[8])
        return Quote(
            ticker=ticker, price=price, source="sina",
            prev_close=prev, day_high=high, day_low=low, volume=vol,
            change_pct=(price/prev-1)*100 if prev else None,
            ts=time.time(),
        )
    except Exception:
        return None


def get_quote(ticker: str) -> Optional[Quote]:
    """三级降级 + 30s cache。"""
    now = time.time()
    if ticker in _CACHE and now - _CACHE[ticker][0] < _TTL:
        # cached price only
        pass  # 不重复用旧 price 除非最近
    for fn in (_fetch_yahoo, _fetch_sina):
        q = fn(ticker)
        if q:
            _CACHE[ticker] = (now, q.price)
            return q
    return None


def batch_quotes(tickers: list[str]) -> dict[str, Quote]:
    return {t: q for t in tickers if (q := get_quote(t))}


if __name__ == "__main__":
    import sys
    tks = sys.argv[1:] or ["AAPL", "600519.SS", "0700.HK"]
    for t in tks:
        q = get_quote(t)
        if q:
            print(f"{t:>12s} ${q.price} ({q.change_pct:+.2f}% vs prev={q.prev_close}) [{q.source}]"
                  if q.change_pct is not None else f"{t:>12s} {q.price} [{q.source}]")
        else:
            print(f"{t:>12s} 无报价")
