"""D5 Compliance — ST / 停牌 / 黑名单 检查。

数据源：
  push2.eastmoney.com/api/qt/stock/get  → f58 (名称) f292 (状态)
本地黑名单：configs/blacklist.txt  (每行一个 ticker)
停牌启发：最近 3 个交易日 volume 均为 0 视为停牌
"""
from __future__ import annotations
import os, asyncio
from datetime import date
import httpx

from core.schemas import MarketData, RiskCheckResult


_CACHE: dict[str, dict] = {}


def _secid(ticker: str) -> str:
    t = ticker.upper()
    if t.endswith(".SS") or t.endswith(".SH"):
        return f"1.{t.split('.')[0]}"
    if t.endswith(".SZ"):
        return f"0.{t.split('.')[0]}"
    if t.endswith(".HK"):
        return f"116.{t.split('.')[0].zfill(5)}"
    return f"105.{t}"


async def _quote_status(ticker: str) -> dict | None:
    if ticker in _CACHE:
        return _CACHE[ticker]
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {"secid": _secid(ticker), "fields": "f57,f58,f292,f43"}
    try:
        async with httpx.AsyncClient(timeout=8, trust_env=True,
                                     headers={"User-Agent": "Mozilla/5.0"}) as c:
            r = await c.get(url, params=params)
            r.raise_for_status()
            js = r.json()
    except Exception:
        return None
    d = js.get("data") or {}
    if not d:
        return None
    _CACHE[ticker] = d
    return d


def _load_blacklist() -> set[str]:
    fp = os.path.join(os.path.dirname(__file__), "..", "configs", "blacklist.txt")
    if not os.path.exists(fp):
        return set()
    with open(fp) as fh:
        return {ln.strip().upper() for ln in fh if ln.strip() and not ln.startswith("#")}


async def compliance_check(ticker: str, md: MarketData | None) -> RiskCheckResult:
    reasons: list[str] = []
    forced = None

    # 1) 黑名单
    bl = _load_blacklist()
    if ticker.upper() in bl:
        reasons.append("命中本地黑名单")
        forced = "block"

    # 2) 名称/ST/退市
    q = await _quote_status(ticker)
    if q:
        name = q.get("f58") or ""
        status = q.get("f292")  # 13 正常
        if "ST" in name or "*ST" in name:
            reasons.append(f"ST/*ST 股: {name}")
            forced = "block"
        if "退" in name:
            reasons.append(f"退市股: {name}")
            forced = "block"
        # 状态码非 13 视为异常（停牌/暂停交易）—— 仅 A 股启用
        t_upper = ticker.upper()
        is_a_share = t_upper.endswith((".SS", ".SH", ".SZ"))
        if is_a_share and status is not None and status not in (13, "13"):
            reasons.append(f"状态码 f292={status}，非正常交易")
            forced = "block"

    # 3) 停牌启发：最近 3 天 volume 都是 0
    if md and md.bars:
        recent = md.bars[-3:]
        if len(recent) == 3 and all((b.volume or 0) <= 0 for b in recent):
            reasons.append("近 3 日成交量为 0，疑似停牌")
            forced = "block"

    passed = forced is None
    return RiskCheckResult(level="compliance", passed=passed,
                          reasons=reasons or ["合规检查通过"],
                          forced_action=forced)
