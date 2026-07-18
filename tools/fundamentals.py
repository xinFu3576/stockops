"""D1 FundamentalsAgent — A 股 F10 财报接口 (最近 8 期)。

字段映射：
  BASIC_EPS         每股收益
  WEIGHTAVG_ROE     加权 ROE
  TOTAL_OPERATE_INCOME  营收
  PARENT_NETPROFIT  归母净利
  XSMLL             销售毛利率
  YSTZ              营收同比 %
  SJLTZ             净利同比 %
  BPS               每股净资产
"""
from __future__ import annotations
import json
from datetime import date
from typing import Optional
import httpx
import os

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".cache", "fundamentals")


async def _fetch_raw(code: str, pages: int = 8) -> list[dict]:
    url = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
    params = {
        "reportName": "RPT_LICO_FN_CPD",
        "columns": "ALL",
        "filter": f"(SECURITY_CODE=\"{code}\")",
        "pageNumber": "1", "pageSize": str(pages),
        "sortColumns": "REPORTDATE", "sortTypes": "-1",
        "source": "HSF10", "client": "PC",
    }
    async with httpx.AsyncClient(timeout=15, trust_env=True,
                                 headers={"User-Agent": "Mozilla/5.0"}) as c:
        r = await c.get(url, params=params)
        r.raise_for_status()
        js = r.json()
    return ((js.get("result") or {}).get("data") or [])


def _cache_path(code: str) -> str:
    return os.path.join(CACHE_DIR, f"{code}.json")


async def fetch_fundamentals(ticker: str, as_of: date, use_cache: bool = True) -> dict | None:
    """返回汇总字典 (最新一期为主，附带 4 期同比/环比)。非 A 股返回 None。"""
    t = ticker.upper()
    if not (t.endswith(".SS") or t.endswith(".SH") or t.endswith(".SZ")):
        return None
    code = t.split(".")[0]

    cache_fp = _cache_path(code)
    if use_cache and os.path.exists(cache_fp):
        try:
            with open(cache_fp) as fh:
                data = json.load(fh)
        except Exception:
            data = None
    else:
        data = None

    if data is None:
        try:
            data = await _fetch_raw(code)
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(cache_fp, "w") as fh:
                json.dump(data, fh, ensure_ascii=False)
        except Exception:
            return None

    # 过滤：只用 as_of 前公布的报表
    def _report_ok(row):
        nd = row.get("NOTICE_DATE") or row.get("UPDATE_DATE") or ""
        return nd[:10] <= as_of.isoformat()

    valid = [r for r in data if _report_ok(r)]
    if not valid:
        return None

    latest = valid[0]

    def _f(k):
        v = latest.get(k)
        return float(v) if v not in (None, "", "None") else None

    return {
        "code": code,
        "as_of": as_of.isoformat(),
        "report_date": latest.get("REPORTDATE", "")[:10],
        "data_type": latest.get("DATATYPE"),
        "sector": latest.get("BOARD_NAME"),
        "eps": _f("BASIC_EPS"),
        "roe_weighted": _f("WEIGHTAVG_ROE"),         # %
        "revenue": _f("TOTAL_OPERATE_INCOME"),        # 元
        "net_profit": _f("PARENT_NETPROFIT"),         # 元
        "gross_margin": _f("XSMLL"),                  # %
        "revenue_yoy": _f("YSTZ"),                    # %
        "netprofit_yoy": _f("SJLTZ"),                 # %
        "bps": _f("BPS"),
    }


if __name__ == "__main__":
    import asyncio
    from datetime import date as _d
    for tk in ("600519.SS", "000858.SZ", "AAPL"):
        d = asyncio.run(fetch_fundamentals(tk, _d.today()))
        print(tk, "->", d)
