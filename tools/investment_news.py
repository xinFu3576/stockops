"""投资信息源多路聚合(免登录):
- 宏观 / 政策 / 央行:
  * xinhuanet.com 财经首页 RSS (CN)
  * fedstats: fed.gov RSS + treasury.gov RSS
- 市场热点:
  * eastmoney 财经首页 (7×24)
  * cls.cn 财联社实时电报 (JSON)
  * yahoo finance top news RSS (US)
- 公司公告:
  * sec.gov EDGAR RSS
  * cninfo 沪深公告(A 股)

设计:
1. 免鉴权,失败源静默降级
2. 统一 NewsItem(title, url, source, ts, tickers[], sentiment_hint, tags)
3. 内置去重(URL 归一化 + title 相似度)
4. 支持关键词过滤 + ticker 关联
5. 结果落 data/news_cache/<date>.json,dashboard 可读
"""
from __future__ import annotations
import asyncio, json, hashlib, re
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from typing import Optional
import httpx
from xml.etree import ElementTree as ET

CACHE = Path(__file__).resolve().parent.parent / "data" / "news_cache"
CACHE.mkdir(parents=True, exist_ok=True)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 Chrome/125 Safari/537.36"
TIMEOUT = httpx.Timeout(12.0, connect=6.0)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": UA}, trust_env=True, follow_redirects=True)


def _hash(url: str, title: str) -> str:
    # URL 归一化 + 标题前 40 字符
    u = re.sub(r'[?&#].*$', '', url or '')
    key = f"{u}|{(title or '')[:40]}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def _norm(items: list[dict]) -> list[dict]:
    """URL+title 去重,按时间倒序。"""
    seen = set(); out = []
    for it in sorted(items, key=lambda x: x.get("ts") or "", reverse=True):
        h = _hash(it.get("url",""), it.get("title",""))
        if h in seen: continue
        seen.add(h)
        out.append(it)
    return out




# ============== 情感打分 (news → sentiment score) ==============

_POS_CN = {"涨":1.0,"利好":1.5,"上调":1.0,"回购":1.2,"分红":0.8,"创新高":1.5,"突破":1.0,
           "超预期":1.5,"中标":1.0,"扩产":1.0,"增长":1.0,"增持":1.2,"看好":1.0,"受益":0.8,
           "反弹":0.6,"降息":1.2,"降准":1.2,"减税":1.0,"利率下调":1.2}
_NEG_CN = {"跌":-1.0,"下跌":-1.0,"下调":-1.0,"利空":-1.5,"减持":-1.2,"亏损":-1.5,"退市":-2.0,
           "ST":-2.0,"警示":-1.0,"问询":-0.8,"违规":-1.5,"处罚":-1.5,"立案":-2.0,"调查":-1.0,
           "诉讼":-1.0,"减产":-0.8,"低于预期":-1.2,"承压":-0.6,"加息":-1.2,"暴跌":-2.0,
           "地震":-0.8,"战争":-1.5,"制裁":-1.5,"衰退":-1.5,"违约":-1.5,"破产":-2.0}
_POS_EN = {"beat":1.5,"upgrade":1.2,"buyback":1.2,"dividend":0.8,"record high":1.5,
           "breakthrough":1.0,"outperform":1.2,"rate cut":1.2,"strong":0.8,"acquire":0.6,
           "surge":1.0,"rally":1.0,"gain":0.6,"raise guidance":1.5,"partnership":0.6}
_NEG_EN = {"miss":-1.5,"downgrade":-1.2,"sell":-1.0,"loss":-1.5,"cut guidance":-1.5,
           "recession":-1.5,"lawsuit":-1.0,"investigation":-1.0,"fraud":-2.0,"delisting":-2.0,
           "sanction":-1.5,"war":-1.5,"crash":-2.0,"plunge":-1.5,"decline":-0.6,
           "rate hike":-1.2,"default":-1.5,"bankrupt":-2.0}


def score_headline(title: str, summary: str = "") -> float:
    """基于中英双语金融词典对单条 headline 打分,归一化到 [-1, 1]。"""
    text = (title + " " + (summary or "")).lower()
    s = 0.0
    for k, v in _POS_CN.items():
        if k in text: s += v
    for k, v in _NEG_CN.items():
        if k in text: s += v
    for k, v in _POS_EN.items():
        if k in text.lower(): s += v
    for k, v in _NEG_EN.items():
        if k in text.lower(): s += v
    # tanh 归一化避免长文本堆叠
    import math
    return math.tanh(s / 3.0)


def enrich_sentiment(items: list[dict]) -> list[dict]:
    """给每条 item 附加 sentiment_score + sentiment_label。"""
    for it in items:
        sc = score_headline(it.get("title",""), it.get("summary",""))
        it["sentiment_score"] = round(sc, 3)
        it["sentiment_label"] = "positive" if sc > 0.15 else ("negative" if sc < -0.15 else "neutral")
    return items


def aggregate_sentiment(items: list[dict], tickers: list[str] | None = None) -> dict:
    """按 ticker 汇总 sentiment(供 analyst 输入)。"""
    from collections import defaultdict
    tks = {t.upper() for t in (tickers or [])}
    bucket: dict = defaultdict(list)
    for it in items:
        sc = it.get("sentiment_score")
        if sc is None: sc = score_headline(it.get("title",""), it.get("summary",""))
        # 全市场情绪
        bucket["_MARKET"].append(sc)
        for tk in it.get("tickers", []):
            tku = tk.upper()
            if not tks or tku in tks:
                bucket[tku].append(sc)
    out = {}
    for k, vs in bucket.items():
        if not vs: continue
        avg = sum(vs)/len(vs)
        # 极端情绪(|score| > 0.5)条数
        extreme = sum(1 for v in vs if abs(v) > 0.5)
        out[k] = {
            "avg": round(avg, 3),
            "count": len(vs),
            "extreme_count": extreme,
            "min": round(min(vs), 3), "max": round(max(vs), 3),
            "label": "positive" if avg > 0.15 else ("negative" if avg < -0.15 else "neutral"),
        }
    return out


# ============== 源实现 ==============

async def _rss(client: httpx.AsyncClient, url: str, source: str, tag: str) -> list[dict]:
    try:
        r = await client.get(url)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        items = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            desc = (item.findtext("description") or "").strip()[:400]
            items.append({
                "title": title, "url": link, "source": source,
                "ts": _parse_rfc(pub), "summary": desc, "tags": [tag],
                "tickers": [],
            })
        return items
    except Exception as e:
        return []


def _parse_rfc(s: str) -> str:
    """RFC-822 → ISO(UTC)。解析失败返回"未知"标记以便打分函数低置信度处理。"""
    if not s: 
        return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt is None: return ""
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


async def fetch_cls_telegraph(client: httpx.AsyncClient) -> list[dict]:
    """新浪财经 7x24 快讯(替代 CLS,免登录 稳定)。原名保留兼容。"""
    try:
        r = await client.get(
            "https://zhibo.sina.com.cn/api/zhibo/feed",
            params={"page": 1, "page_size": 40, "zhibo_id": 152, "tag_id": 0, "dire": "f", "dpc": 1},
        )
        r.raise_for_status()
        data = r.json()
        feed = (((data.get("result") or {}).get("data") or {}).get("feed") or {}).get("list") or []
        out = []
        for e in feed:
            title = (e.get("rich_text") or e.get("summary") or "").strip()
            if not title: continue
            ts_raw = e.get("create_time") or ""
            try:
                dt = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S")
                ts = dt.replace(tzinfo=timezone(timedelta(hours=8))).astimezone(timezone.utc).isoformat()
            except Exception:
                ts = datetime.now(timezone.utc).isoformat()
            out.append({
                "title": title[:180],
                "url": e.get("docurl") or f"https://finance.sina.com.cn/7x24/",
                "source": "sina_7x24",
                "ts": ts,
                "summary": (e.get("rich_text") or "")[:400],
                "tags": ["market_hot", "cn"],
                "tickers": _extract_a_tickers(title),
            })
        return out
    except Exception:
        return []


def _extract_a_tickers(text: str) -> list[str]:
    """从中文文本抽 A 股代码: 6xxxxx.SS / 000xxx / 300xxx / 002xxx.SZ。"""
    out = set()
    for m in re.finditer(r'(?<!\d)(\d{6})(?!\d)', text):
        code = m.group(1)
        if code.startswith(("60", "68", "90")): out.add(f"{code}.SS")
        elif code.startswith(("00", "30", "20")): out.add(f"{code}.SZ")
    return sorted(out)


async def fetch_yahoo_top(client: httpx.AsyncClient) -> list[dict]:
    """Yahoo Finance RSS 头条(US)。"""
    return await _rss(client, "https://finance.yahoo.com/news/rssindex", "yahoo_finance", "us")


async def fetch_sec_edgar(client: httpx.AsyncClient) -> list[dict]:
    """SEC EDGAR 最新公告 (10-K/10-Q/8-K)。"""
    return await _rss(client,
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&company=&output=atom",
        "sec_edgar", "us_filings")


async def fetch_fed_rss(client: httpx.AsyncClient) -> list[dict]:
    """Fed 官网 press release。"""
    return await _rss(client, "https://www.federalreserve.gov/feeds/press_all.xml", "fed", "policy")


async def fetch_treasury_rss(client: httpx.AsyncClient) -> list[dict]:
    return await _rss(client, "https://home.treasury.gov/news/press-releases/feed", "us_treasury", "policy")


async def fetch_eastmoney_hot(client: httpx.AsyncClient) -> list[dict]:
    """东方财富 7×24 快讯。"""
    try:
        r = await client.get("https://np-listapi.eastmoney.com/comm/wap/getListInfo",
                             params={"client": "wap", "biz": "web_724", "pageSize": 50,
                                     "type": "1", "column": "syl", "callback": ""})
        r.raise_for_status()
        text = r.text.strip()
        if text.startswith("("): text = text[1:-1]
        data = json.loads(text)
        arr = ((data.get("data") or {}).get("list")) or []
        out = []
        for e in arr:
            title = (e.get("title") or "").strip()
            if not title: continue
            pub = e.get("showTime") or e.get("createTime") or ""
            out.append({
                "title": title[:200],
                "url": e.get("url") or e.get("Url") or "",
                "source": "eastmoney_724",
                "ts": pub,
                "summary": (e.get("digest") or "")[:400],
                "tags": ["market_hot", "cn"],
                "tickers": _extract_a_tickers(title),
            })
        return out
    except Exception:
        return []


async def fetch_xinhua(client: httpx.AsyncClient) -> list[dict]:
    """新华社财经 RSS。"""
    return await _rss(client, "http://www.xinhuanet.com/politics/news_politics.xml", "xinhua", "policy_cn")


async def fetch_all(sources: Optional[list[str]] = None) -> list[dict]:
    """并发抓取所有源。sources=None → 全部;否则只跑指定源名。"""
    registry = {
        "cls": fetch_cls_telegraph,
        "eastmoney": fetch_eastmoney_hot,
        "yahoo": fetch_yahoo_top,
        "sec": fetch_sec_edgar,
        "fed": fetch_fed_rss,
        "treasury": fetch_treasury_rss,
        "xinhua": fetch_xinhua,
        "wallstreetcn": fetch_wallstreetcn,
        "weibo": fetch_weibo_finance,
        "x": fetch_x_stub,
    }
    picks = [(k, v) for k, v in registry.items() if not sources or k in sources]
    async with _client() as client:
        results = await asyncio.gather(*[fn(client) for _, fn in picks], return_exceptions=True)
    all_items: list[dict] = []
    stats: dict[str, int] = {}
    for (name, _), r in zip(picks, results):
        if isinstance(r, Exception):
            stats[name] = 0
            continue
        stats[name] = len(r or [])
        all_items.extend(r or [])
    all_items = _norm(all_items)
    all_items = enrich_sentiment(all_items)
    return all_items


def keyword_filter(items: list[dict], keywords: list[str]) -> list[dict]:
    kws = [k.lower() for k in keywords if k]
    if not kws: return items
    out = []
    for it in items:
        blob = (it.get("title","") + " " + it.get("summary","")).lower()
        if any(k in blob for k in kws):
            out.append(it)
    return out


def ticker_filter(items: list[dict], tickers: list[str]) -> list[dict]:
    tks = {t.upper() for t in tickers}
    if not tks: return items
    out = []
    for it in items:
        it_tks = {t.upper() for t in it.get("tickers", [])}
        if it_tks & tks:
            out.append(it)
    return out


def _score_urgency(item: dict) -> float:
    """紧迫度 0..1: 政策 / 央行 / 公告 优先,时间越新越高。"""
    s = 0.3
    tags = item.get("tags", [])
    if "policy" in tags or "policy_cn" in tags: s += 0.35
    if "us_filings" in tags: s += 0.25
    src = item.get("source","")
    if src in ("cls_telegraph","fed"): s += 0.15
    ts_str = item.get("ts","") or ""
    if not ts_str:
        s *= 0.4   # 无时间戳的强降级
    else:
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z","+00:00"))
            age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
            if age_h < 3: s += 0.15
            elif age_h < 12: s += 0.08
            elif age_h < 48: s -= 0.05
            elif age_h < 24*30: s *= 0.5
            else: s *= 0.15
        except Exception: s *= 0.4
    return max(0.0, min(1.0, s))


def save_snapshot(items: list[dict], as_of: date | None = None) -> Path:
    as_of = as_of or date.today()
    fp = CACHE / f"{as_of.isoformat()}.json"
    fp.write_text(json.dumps({
        "as_of": as_of.isoformat(),
        "count": len(items),
        "items": items,
    }, ensure_ascii=False, indent=2, default=str))
    return fp


def load_latest() -> dict | None:
    files = sorted(CACHE.glob("*.json"), reverse=True)
    if not files: return None
    return json.loads(files[0].read_text())


# ============== CLI ==============

def _digest_md(items: list[dict], top: int = 30) -> str:
    lines = [f"# 投资信息源快讯 · {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             f"抓取 {len(items)} 条 (去重后),按紧迫度取前 {min(top, len(items))} 条:\n"]
    for it in sorted(items, key=lambda x: -_score_urgency(x))[:top]:
        tks = ",".join(it.get("tickers", [])[:5])
        tag = ",".join(it.get("tags", []))
        line = f"- **[{it.get('source')}]** [{it.get('title','')[:120]}]({it.get('url','')})"
        if tks: line += f" `{tks}`"
        if tag: line += f" _{tag}_"
        lines.append(line)
    return "\n".join(lines)


async def _cli():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", help="逗号分隔源名(cls/eastmoney/yahoo/sec/fed/treasury/xinhua),不填=全部")
    ap.add_argument("--keywords", help="关键词过滤,逗号分隔")
    ap.add_argument("--tickers", help="仅保留提到这些 ticker 的新闻,逗号分隔")
    ap.add_argument("--top", type=int, default=30, help="digest 前 N 条")
    ap.add_argument("--save", action="store_true", help="落 data/news_cache/<date>.json")
    ap.add_argument("--json", action="store_true", help="直接输出 JSON")
    ap.add_argument("--notify", action="store_true", help="推送 digest 到 notify 渠道")
    args = ap.parse_args()

    sources = args.sources.split(",") if args.sources else None
    items = await fetch_all(sources)
    if args.keywords:
        items = keyword_filter(items, args.keywords.split(","))
    if args.tickers:
        items = ticker_filter(items, args.tickers.split(","))

    if args.save:
        fp = save_snapshot(items)
        print(f"[news] saved → {fp}")

    if args.json:
        print(json.dumps({"count": len(items), "items": items[:args.top]},
                          ensure_ascii=False, indent=2, default=str))
    else:
        md = _digest_md(items, args.top)
        print(md)

    if args.notify:
        from tools.notify import notify
        r = notify(f"投资情报 · {datetime.now().strftime('%m-%d %H:%M')}", _digest_md(items, args.top))
        print(f"[notify] {r}")


if __name__ == "__main__":
    asyncio.run(_cli())


# ============== v0.8.0 新增数据源 ==============

async def fetch_wallstreetcn(client: httpx.AsyncClient) -> list[dict]:
    """华尔街见闻实时快讯 API（免登录 稳定）。"""
    try:
        r = await client.get(
            "https://api-one-wscn.awtmt.com/apiv1/content/lives",
            params={"channel": "global-channel", "client": "pc", "limit": 40},
        )
        r.raise_for_status()
        data = r.json()
        items = ((data.get("data") or {}).get("items") or [])
        out = []
        for e in items:
            title = (e.get("title") or e.get("content_text") or "").strip()
            if not title: continue
            ts_raw = e.get("display_time") or e.get("created_at")
            try:
                dt = datetime.fromtimestamp(int(ts_raw), tz=timezone.utc)
                ts = dt.isoformat()
            except Exception:
                ts = datetime.now(timezone.utc).isoformat()
            out.append({
                "title": title[:180],
                "url": e.get("uri") or "https://wallstreetcn.com/live",
                "source": "wallstreetcn",
                "ts": ts,
                "summary": (e.get("content_text") or "")[:400],
                "tags": ["market_hot", "global"],
                "tickers": _extract_a_tickers(title),
            })
        return out
    except Exception:
        return []


async def fetch_weibo_finance(client: httpx.AsyncClient) -> list[dict]:
    """微博财经热搜 (best-effort)。"""
    try:
        r = await client.get(
            "https://m.weibo.cn/api/container/getIndex",
            params={"containerid": "231583"},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://m.weibo.cn/"},
            timeout=10.0,
        )
        r.raise_for_status()
        data = r.json()
        cards = ((data.get("data") or {}).get("cards") or [])
        out = []
        for c in cards:
            groups = c.get("card_group") or ([c] if c.get("desc") else [])
            for g in groups:
                text = (g.get("desc") or g.get("desc1") or "").strip()
                if not text or len(text) < 4: continue
                out.append({
                    "title": text[:180],
                    "url": g.get("scheme") or "https://m.weibo.cn/",
                    "source": "weibo_finance",
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "summary": (g.get("desc1") or "")[:200],
                    "tags": ["social", "cn"],
                    "tickers": _extract_a_tickers(text),
                })
        return out[:40]
    except Exception:
        return []


async def fetch_x_stub(client: httpx.AsyncClient) -> list[dict]:
    """X/Twitter via nitter (best-effort，多为降级空返)。"""
    for mirror in ("https://nitter.privacydev.net", "https://nitter.net"):
        try:
            r = await client.get(f"{mirror}/search/rss",
                                 params={"q": "$SPY OR $QQQ OR Fed OR CPI", "f": "tweets"},
                                 timeout=8.0)
            if r.status_code != 200: continue
            import re
            txt = r.text
            titles = re.findall(r"<title><!\[CDATA\[(.+?)\]\]></title>", txt)[1:]
            links = re.findall(r"<link>(.+?)</link>", txt)[1:]
            out = []
            for t, l in zip(titles[:30], links[:30]):
                out.append({
                    "title": t[:180],
                    "url": l,
                    "source": "x_via_nitter",
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "summary": "",
                    "tags": ["social", "global"],
                    "tickers": _extract_a_tickers(t),
                })
            if out: return out
        except Exception:
            continue
    return []
