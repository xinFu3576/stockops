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
_TTL = 300  # 5 分钟缓存

_CTX = ssl.create_default_context()


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


def fetch_options_skew(ticker: str) -> Optional[OptionsSkew]:
    """三级降级：Tradier → Polygon → None(caller 用 proxy)。带 5min 缓存。"""
    key = f"opt::{ticker}"
    now = time.time()
    if key in _CACHE and now - _CACHE[key][0] < _TTL:
        return OptionsSkew(**_CACHE[key][1]) if _CACHE[key][1] else None
    for fn in (fetch_tradier, fetch_polygon):
        r = fn(ticker)
        if r and (r.iv_skew is not None or r.put_call_ratio is not None):
            _CACHE[key] = (now, r.__dict__.copy())
            return r
    _CACHE[key] = (now, None)
    return None


def health() -> dict:
    """给 broker-health 显示 options 数据源状态。"""
    r = {}
    r["tradier"] = "ok" if os.environ.get("TRADIER_API_KEY") else "no_key"
    r["polygon"] = "ok" if os.environ.get("POLYGON_API_KEY") else "no_key"
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
