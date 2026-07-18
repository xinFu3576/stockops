"""真实 options chain 抓取器：Tradier → Polygon → 代理 三级降级。

真 IV skew = 25-delta put IV - 25-delta call IV (30D ATM 近月)
无 API key 时退到 microstructure.iv_skew_proxy 的 realized-vol 代理。

环境变量：
  TRADIER_API_KEY  (免费 sandbox: https://developer.tradier.com/)
  POLYGON_API_KEY  (免费 Basic: https://polygon.io/)
"""
from __future__ import annotations
import os, math, time, urllib.request, urllib.parse, json, ssl
from dataclasses import dataclass, field
from typing import Optional
from datetime import date, datetime, timedelta

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL = 300  # 5 分钟内存缓存
_DISK_TTL = 1800  # 30 分钟磁盘缓存 (T+0 IV skew 刷新)

from pathlib import Path as _P
_CACHE_DIR = _P(__file__).resolve().parent.parent / "data" / "options_cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_CTX = ssl.create_default_context()


def _disk_load(ticker: str) -> Optional[dict]:
    f = _CACHE_DIR / f"{ticker.replace('/','_')}.json"
    if not f.exists(): return None
    try:
        d = json.loads(f.read_text())
        if time.time() - d.get("_ts", 0) > _DISK_TTL: return None
        return d
    except Exception:
        return None


def _disk_save(ticker: str, obj: dict):
    f = _CACHE_DIR / f"{ticker.replace('/','_')}.json"
    try:
        obj = dict(obj); obj["_ts"] = time.time()
        f.write_text(json.dumps(obj, default=str, ensure_ascii=False, indent=2))
    except Exception:
        pass


@dataclass
class OptionsSkew:
    """options-implied 情绪指标包。"""
    ticker: str
    source: str                        # tradier / polygon / proxy
    spot: Optional[float] = None
    expiry: Optional[str] = None
    atm_call_iv: Optional[float] = None
    atm_put_iv: Optional[float] = None
    iv_skew: Optional[float] = None    # put_iv - call_iv (正 = 恐慌溢价)
    put_call_ratio: Optional[float] = None   # OI 或成交量
    n_contracts: int = 0

    def as_factors(self) -> dict:
        return {
            "iv_skew_real": self.iv_skew,
            "atm_iv": (self.atm_call_iv + self.atm_put_iv) / 2 if self.atm_call_iv and self.atm_put_iv else None,
            "put_call_ratio": self.put_call_ratio,
        }


def _get_json(url: str, headers: dict | None = None, timeout: float = 8.0) -> dict | None:
    try:
        req = urllib.request.Request(url, headers=headers or {})
        r = urllib.request.urlopen(req, context=_CTX, timeout=timeout)
        return json.loads(r.read().decode())
    except Exception:
        return None


def _pick_near_expiry(expirations: list[str], target_days: int = 30) -> Optional[str]:
    """挑最接近 30D 的到期日。"""
    today = date.today()
    best, best_gap = None, 9999
    for e in expirations:
        try:
            d = datetime.strptime(e, "%Y-%m-%d").date()
        except Exception:
            continue
        gap = abs((d - today).days - target_days)
        if gap < best_gap:
            best_gap, best = gap, e
    return best


# ============== Tradier ==============
def fetch_tradier(ticker: str) -> Optional[OptionsSkew]:
    token = os.environ.get("TRADIER_API_KEY")
    if not token: return None
    base = os.environ.get("TRADIER_BASE", "https://api.tradier.com/v1")
    H = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    # 1) spot 报价
    q = _get_json(f"{base}/markets/quotes?symbols={ticker}", H)
    if not q: return None
    quote = ((q.get("quotes") or {}).get("quote") or {})
    spot = quote.get("last") or quote.get("close")

    # 2) 到期日列表
    e = _get_json(f"{base}/markets/options/expirations?symbol={ticker}", H)
    if not e: return None
    exps = ((e.get("expirations") or {}).get("date") or [])
    if isinstance(exps, str): exps = [exps]
    expiry = _pick_near_expiry(exps)
    if not expiry: return None

    # 3) chain
    c = _get_json(f"{base}/markets/options/chains?symbol={ticker}&expiration={expiry}&greeks=true", H)
    if not c: return None
    opts = ((c.get("options") or {}).get("option") or [])
    if not opts: return None

    return _agg_chain(ticker, "tradier", spot, expiry, opts,
                       strike_key="strike", type_key="option_type",
                       iv_getter=lambda o: (o.get("greeks") or {}).get("mid_iv"),
                       oi_key="open_interest", vol_key="volume",
                       type_call="call", type_put="put")


# ============== Polygon ==============
def fetch_polygon(ticker: str) -> Optional[OptionsSkew]:
    key = os.environ.get("POLYGON_API_KEY")
    if not key: return None
    base = "https://api.polygon.io"
    # 1) spot
    q = _get_json(f"{base}/v2/last/trade/{ticker}?apiKey={key}")
    spot = ((q or {}).get("results") or {}).get("p")

    # 2) options snapshot(免费级支持)
    url = f"{base}/v3/snapshot/options/{ticker}?limit=250&apiKey={key}"
    d = _get_json(url)
    if not d: return None
    contracts = d.get("results", [])
    if not contracts: return None

    # 挑最接近 30D 的到期
    from collections import defaultdict
    by_exp: dict[str, list] = defaultdict(list)
    for c in contracts:
        exp = ((c.get("details") or {}).get("expiration_date"))
        if exp: by_exp[exp].append(c)
    expiry = _pick_near_expiry(list(by_exp.keys()))
    if not expiry: return None
    opts = by_exp[expiry]

    return _agg_chain(ticker, "polygon", spot, expiry, opts,
                       strike_key=None,
                       type_key=None,
                       # polygon 结构: details.strike_price / details.contract_type / implied_volatility / open_interest / day.volume
                       strike_getter=lambda o: (o.get("details") or {}).get("strike_price"),
                       type_getter=lambda o: (o.get("details") or {}).get("contract_type"),
                       iv_getter=lambda o: o.get("implied_volatility"),
                       oi_getter=lambda o: o.get("open_interest"),
                       vol_getter=lambda o: (o.get("day") or {}).get("volume"),
                       type_call="call", type_put="put")


def _agg_chain(ticker, source, spot, expiry, opts, *,
               strike_key=None, type_key=None, iv_getter,
               oi_key=None, vol_key=None,
               strike_getter=None, type_getter=None,
               oi_getter=None, vol_getter=None,
               type_call="call", type_put="put") -> OptionsSkew:
    """通用聚合：找 ATM ±5% call/put，加权 IV 平均。"""
    strike_of = strike_getter or (lambda o: o.get(strike_key))
    type_of = type_getter or (lambda o: o.get(type_key))
    oi_of = oi_getter or ((lambda o: o.get(oi_key)) if oi_key else (lambda o: 0))
    vol_of = vol_getter or ((lambda o: o.get(vol_key)) if vol_key else (lambda o: 0))

    if not spot:
        return OptionsSkew(ticker=ticker, source=source, expiry=expiry, n_contracts=len(opts))

    calls, puts = [], []
    call_oi = put_oi = 0
    call_vol = put_vol = 0
    for o in opts:
        try:
            s = float(strike_of(o) or 0)
            t = (type_of(o) or "").lower()
            iv = iv_getter(o)
            oi = int(oi_of(o) or 0)
            vol = int(vol_of(o) or 0)
        except Exception:
            continue
        if s <= 0: continue
        # ATM ±5%
        if abs(s - spot) / spot <= 0.05 and iv is not None and 0 < iv < 5.0:
            if t == type_call: calls.append((s, float(iv), oi))
            elif t == type_put: puts.append((s, float(iv), oi))
        # 全量 OI/Vol 用于 P/C ratio
        if t == type_call:
            call_oi += oi; call_vol += vol
        elif t == type_put:
            put_oi += oi; put_vol += vol

    def _w_iv(chain):
        if not chain: return None
        # 用 (1/(|strike-spot|+1e-9)) 加权
        num = sum(iv / (abs(s - spot) + 1e-9) for s, iv, _ in chain)
        den = sum(1.0 / (abs(s - spot) + 1e-9) for s, _, _ in chain)
        return num / den if den else None

    atm_call = _w_iv(calls)
    atm_put = _w_iv(puts)
    skew = (atm_put - atm_call) if (atm_call is not None and atm_put is not None) else None
    pcr = None
    if call_oi > 0: pcr = put_oi / call_oi
    elif call_vol > 0: pcr = put_vol / call_vol

    return OptionsSkew(
        ticker=ticker, source=source, spot=spot, expiry=expiry,
        atm_call_iv=atm_call, atm_put_iv=atm_put, iv_skew=skew,
        put_call_ratio=pcr, n_contracts=len(opts),
    )


# ============== Futu OpenD (HK 期权) ==============
def fetch_futu_hk(ticker: str) -> Optional[OptionsSkew]:
    """通过 FutuOpenD 本地网关抓 HK 期权链。

    需 FutuOpenD 已启动（默认 127.0.0.1:11111）；pip install futu-api。
    Env: FUTU_HOST（默认 127.0.0.1）/ FUTU_PORT（默认 11111）。
    仅 .HK 生效。返回 None 则调用方继续走 proxy 或 iv_skew_proxy 因子。
    """
    tk = ticker.upper()
    if not tk.endswith(".HK"):
        return None
    host = os.environ.get("FUTU_HOST", "127.0.0.1")
    port = int(os.environ.get("FUTU_PORT", "11111"))
    try:
        from futu import OpenQuoteContext, RET_OK  # type: ignore
    except Exception:
        return None
    code = tk.replace(".HK", "").zfill(5)
    hk_code = f"HK.{code}"
    ctx = OpenQuoteContext(host=host, port=port)
    try:
        # 1) spot
        ret, sq = ctx.get_market_snapshot([hk_code])
        spot = None
        if ret == RET_OK and len(sq) > 0:
            spot = float(sq["last_price"].iloc[0])
        # 2) 期权到期日
        ret, expirations = ctx.get_option_expiration_date(hk_code)
        if ret != RET_OK or expirations is None or len(expirations) == 0:
            return None
        # 挑最接近 30 天
        exps = [str(e) for e in expirations["strike_time"].tolist()]
        expiry = _pick_near_expiry(exps, target_days=30)
        if not expiry:
            expiry = exps[0]
        # 3) 期权链
        ret, chain = ctx.get_option_chain(hk_code, start=expiry, end=expiry)
        if ret != RET_OK or chain is None or len(chain) == 0:
            return None
        # 转换成通用结构
        rows = chain.to_dict(orient="records")
        opts = []
        for row in rows:
            t = row.get("option_type") or ""
            opts.append({
                "strike": row.get("strike_price"),
                "type": "call" if "CALL" in t.upper() else ("put" if "PUT" in t.upper() else t),
                "iv": row.get("implied_volatility") or row.get("iv"),
                "oi": row.get("open_interest") or 0,
                "vol": row.get("volume") or 0,
            })
        return _agg_chain(ticker, "futu_hk", spot, expiry, opts,
                          strike_key="strike", type_key="type",
                          iv_getter=lambda o: o.get("iv"),
                          oi_key="oi", vol_key="vol",
                          type_call="call", type_put="put")
    except Exception as e:
        return None
    finally:
        try: ctx.close()
        except Exception: pass


# ============== aastocks HK 期权（简易 HTML 解析） ==============
def fetch_aastocks_hk(ticker: str) -> Optional[OptionsSkew]:
    """HK 期权兜底：aastocks.com Options Snapshot。只解析总量 P/C，无 IV skew。"""
    tk = ticker.upper()
    if not tk.endswith(".HK"): return None
    code = tk.replace(".HK", "").lstrip("0") or "0"
    url = f"https://www.aastocks.com/en/stocks/analysis/tools/options-summary/basic-info?symbol={code}"
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        r = urllib.request.urlopen(req, context=_CTX, timeout=8)
        html = r.read().decode("utf-8", errors="ignore")
        # 极简正则找 P/C ratio 数字
        import re
        m = re.search(r"Put[/\\s]*Call.*?(\d+\.\d{2})", html, re.I | re.S)
        pc = float(m.group(1)) if m else None
        if pc is None:
            return None
        return OptionsSkew(
            ticker=ticker, source="aastocks_hk",
            put_call_ratio=pc, n_contracts=0,
        )
    except Exception:
        return None


def fetch_options_skew(ticker: str, force_refresh: bool = False) -> Optional[OptionsSkew]:
    """三级降级：Tradier → Polygon → None(caller 用 proxy)。
    双层缓存：内存 5min + 磁盘 1h（data/options_cache/{ticker}.json）。"""
    key = f"opt::{ticker}"
    now = time.time()
    if not force_refresh:
        if key in _CACHE and now - _CACHE[key][0] < _TTL:
            return OptionsSkew(**_CACHE[key][1]) if _CACHE[key][1] else None
        # 磁盘 fallback
        disk = _disk_load(ticker)
        if disk:
            data = {k: v for k, v in disk.items() if k != "_ts"}
            _CACHE[key] = (now, data)
            return OptionsSkew(**data) if data else None
    # HK 优先走 futu / aastocks
    is_hk = ticker.upper().endswith(".HK")
    chain_fns = ((fetch_futu_hk, fetch_aastocks_hk, fetch_tradier, fetch_polygon)
                 if is_hk else (fetch_tradier, fetch_polygon))
    for fn in chain_fns:
        r = fn(ticker)
        if r and (r.iv_skew is not None or r.put_call_ratio is not None):
            d = r.__dict__.copy()
            _CACHE[key] = (now, d)
            _disk_save(ticker, d)
            return r
    _CACHE[key] = (now, None)
    return None


def cache_stats() -> dict:
    """磁盘缓存统计。"""
    import os as _os
    files = list(_CACHE_DIR.glob("*.json"))
    total_size = sum(f.stat().st_size for f in files)
    return {"n_files": len(files), "total_bytes": total_size,
            "dir": str(_CACHE_DIR), "memory_entries": len(_CACHE)}


def health() -> dict:
    """给 broker-health 显示 options 数据源状态。"""
    r = {}
    r["tradier"] = "ok" if os.environ.get("TRADIER_API_KEY") else "no_key"
    r["polygon"] = "ok" if os.environ.get("POLYGON_API_KEY") else "no_key"
    try:
        import futu  # noqa
        r["futu_hk"] = "ok_lib"
    except Exception:
        r["futu_hk"] = "no_lib"
    r["aastocks_hk"] = "http_probe"
    return r


if __name__ == "__main__":
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    s = fetch_options_skew(tk)
    if s:
        print(json.dumps({**s.__dict__, "factors": s.as_factors()}, indent=2, default=str))
    else:
        print(f"[options] {tk} 无 key 或降级为代理")
    print(f"health: {health()}")
