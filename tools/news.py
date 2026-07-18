"""D1 NewsAgent — 从东方财富抓最近新闻 + 公告。"""
from __future__ import annotations
import json, re, asyncio
from datetime import date, datetime, timedelta
from urllib.parse import quote
import httpx

from core.schemas import NewsItem

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 Chrome/125 Safari/537.36",
]
import random
def _ua():
    return random.choice(UAS)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(15.0, connect=8.0),
        headers={"User-Agent": _ua(), "Accept": "*/*"},
        trust_env=True, http2=False,
    )


def _strip_jsonp(text: str) -> str:
    t = text.strip()
    lparen = t.find("(")
    rparen = t.rfind(")")
    if lparen >= 0 and rparen > lparen:
        return t[lparen + 1: rparen]
    return t


def _stock_code(ticker: str) -> tuple[str, str]:
    t = ticker.upper()
    if t.endswith(".SS") or t.endswith(".SH"):
        return t.split(".")[0], "A"
    if t.endswith(".SZ"):
        return t.split(".")[0], "A"
    if t.endswith(".HK"):
        return t.split(".")[0].zfill(4), "HK"
    return t, "US"


async def _eastmoney_search_news(keyword: str, page_size: int = 15) -> list[NewsItem]:
    payload = {
        "uid": "", "keyword": keyword, "type": ["cmsArticleWebOld"],
        "client": "web", "clientVersion": "curr",
        "param": {"cmsArticleWebOld": {"searchScope": "default", "sort": "default",
                                        "pageIndex": 1, "pageSize": page_size}},
    }
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    params = {"cb": "cb", "param": json.dumps(payload, ensure_ascii=False), "_": "1"}
    async with _client() as c:
        r = await c.get(url, params=params)
        r.raise_for_status()
        data = json.loads(_strip_jsonp(r.text))
    items = ((data.get("result") or {}).get("cmsArticleWebOld") or [])
    out: list[NewsItem] = []
    for it in items:
        try:
            ts = datetime.strptime(it["date"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        title = re.sub(r"<[^>]+>", "", it.get("title") or "")
        body = re.sub(r"<[^>]+>", "", it.get("content") or "")
        out.append(NewsItem(ts=ts, title=title, url=it.get("url"),
                            source=it.get("mediaName") or "eastmoney",
                            body=body, lang="zh"))
    return out


async def _eastmoney_announcements(code: str, page_size: int = 10) -> list[NewsItem]:
    url = "https://np-anotice-stock.eastmoney.com/api/security/ann"
    params = {"sr": "-1", "page_size": str(page_size), "page_index": "1",
              "ann_type": "A", "client_source": "web", "stock_list": code,
              "f_node": "0", "s_node": "0"}
    async with _client() as c:
        r = await c.get(url, params=params)
        r.raise_for_status()
        js = r.json()
    items = ((js.get("data") or {}).get("list") or [])
    out: list[NewsItem] = []
    for it in items:
        try:
            ts_str = it.get("display_time") or it.get("notice_date") or ""
            ts_str = ts_str.split(":")[0] + ":" + ts_str.split(":")[1] + ":" + ts_str.split(":")[2] if ts_str.count(":") >= 3 else ts_str
            ts = datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            try:
                ts = datetime.strptime((it.get("notice_date") or "")[:19], "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
        title = it.get("title_ch") or it.get("title") or ""
        out.append(NewsItem(ts=ts, title=title, url=None, source="公告",
                            body=None, lang="zh"))
    return out


async def fetch_news(ticker: str, as_of: date, days: int = 7) -> list[NewsItem]:
    code, market = _stock_code(ticker)
    if market == "A":
        keyword_map = {"600519": "贵州茅台", "000858": "五粮液"}
        keyword = keyword_map.get(code, code)
        try:
            news_task = _eastmoney_search_news(keyword)
            ann_task = _eastmoney_announcements(code)
            news, anns = await asyncio.gather(news_task, ann_task, return_exceptions=True)
            items: list[NewsItem] = []
            if isinstance(news, list): items.extend(news)
            if isinstance(anns, list): items.extend(anns)
        except Exception:
            items = []
    else:
        # 港美股：占位，返回空。真实项目接 Finnhub/Serpapi/NewsAPI
        items = []

    cutoff = datetime.combine(as_of - timedelta(days=days), datetime.min.time())
    upper = datetime.combine(as_of, datetime.max.time())
    return [n for n in items if cutoff <= n.ts <= upper]


if __name__ == "__main__":
    from datetime import date as _d
    news = asyncio.run(fetch_news("600519.SS", _d.today()))
    print("news count:", len(news))
    for n in news[:8]:
        print(f"  [{n.ts.date()}] ({n.source}) {n.title[:60]}")
