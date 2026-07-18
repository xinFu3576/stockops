"""D1 AltDataAgent — 龙虎榜 / 大宗交易 / 宏观 regime。"""
from __future__ import annotations
import json
from datetime import date, timedelta
import asyncio
import httpx

from core.schemas import AltSignal


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(12.0, connect=6.0),
        headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"},
        trust_env=True, http2=False,
    )


def _strip_jsonp(t: str) -> str:
    t = t.strip()
    lp = t.find("("); rp = t.rfind(")")
    if lp >= 0 and rp > lp:
        return t[lp+1:rp]
    return t


async def _lhb_net_buy(code: str, as_of: date) -> float | None:
    """龙虎榜净买入 (元)。当日无上榜返回 None。"""
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "callback": "cb",
        "sortColumns": "SECURITY_CODE", "sortTypes": "1",
        "pageSize": "10", "pageNumber": "1",
        "reportName": "RPT_DAILYBILLBOARD_DETAILS",
        "columns": "ALL", "source": "WEB",
        "filter": f"(TRADE_DATE='{as_of.isoformat()}')(SECURITY_CODE=\"{code}\")",
    }
    try:
        async with _client() as c:
            r = await c.get(url, params=params)
            js = json.loads(_strip_jsonp(r.text))
    except Exception:
        return None
    if not (js.get("result") and js["result"].get("data")):
        return None
    rows = js["result"]["data"]
    net = 0.0
    for row in rows:
        b = row.get("BUY_AMT") or 0
        s = row.get("SELL_AMT") or 0
        net += float(b) - float(s)
    return net


async def _block_trade(code: str, as_of: date) -> float | None:
    """大宗交易当日总成交额 (元)。"""
    url = "https://datacenter-web.eastmoney.com/api/data/v1/get"
    params = {
        "callback": "cb",
        "sortColumns": "TRADE_DATE", "sortTypes": "-1",
        "pageSize": "20", "pageNumber": "1",
        "reportName": "RPT_DAILY_LARGEDEALS",
        "columns": "ALL", "source": "WEB",
        "filter": f"(SECURITY_CODE=\"{code}\")(TRADE_DATE='{as_of.isoformat()}')",
    }
    try:
        async with _client() as c:
            r = await c.get(url, params=params)
            js = json.loads(_strip_jsonp(r.text))
    except Exception:
        return None
    if not (js.get("result") and js["result"].get("data")):
        return None
    total = sum(float(row.get("DEAL_AMT") or 0) for row in js["result"]["data"])
    return total or None


async def _macro_regime(as_of: date) -> str | None:
    """粗糙判断宏观风险偏好：沪深 300 近 20 日趋势 + 波动率。"""
    from tools.market_data import fetch_market_data
    try:
        idx = await fetch_market_data("000300.SS", as_of)
        if len(idx.bars) < 25:
            return "neutral"
        c = [b.close for b in idx.bars[-25:]]
        ret20 = c[-1] / c[0] - 1
        # 20 日日收益标准差
        rets = [c[i]/c[i-1] - 1 for i in range(1, len(c))]
        vol = (sum((r - sum(rets)/len(rets))**2 for r in rets) / len(rets)) ** 0.5
        if ret20 > 0.03 and vol < 0.02:
            return "risk_on"
        if ret20 < -0.03 or vol > 0.03:
            return "risk_off"
        return "neutral"
    except Exception:
        return None


async def fetch_alt(ticker: str, as_of: date) -> AltSignal:
    t = ticker.upper()
    market_kind = "A" if t.endswith((".SS", ".SH", ".SZ")) else "OTHER"
    code = t.split(".")[0]

    regime_task = _macro_regime(as_of)
    if market_kind == "A":
        lhb_task = _lhb_net_buy(code, as_of)
        block_task = _block_trade(code, as_of)
        lhb, block, regime = await asyncio.gather(
            lhb_task, block_task, regime_task, return_exceptions=True
        )
    else:
        regime = await regime_task
        lhb = None; block = None

    def _val(x):
        return None if isinstance(x, Exception) else x

    return AltSignal(
        ticker=ticker, as_of=as_of,
        lhb_net_buy=_val(lhb),
        block_trade_amount=_val(block),
        institution_hold_change=None,
        limit_up_reason=None,
        macro_regime=_val(regime),
    )


if __name__ == "__main__":
    from datetime import date as _d
    for tk in ("600519.SS", "000858.SZ", "AAPL"):
        a = asyncio.run(fetch_alt(tk, _d.today()))
        print(f"{tk:12s} lhb={a.lhb_net_buy} block={a.block_trade_amount} regime={a.macro_regime}")
