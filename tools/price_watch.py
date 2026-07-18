"""分钟级价格预警:轮询实时 quote,若相对上一 snapshot 变动 ≥阈值,推送告警。
用法:
  python -m tools.price_watch --list core --pct 3 --interval 60
  # 只跑一次 snapshot:
  python -m tools.price_watch --list core --once

数据源:
  A 股 (600xxx.SS/000xxx.SZ/0xxxx.HK 通用): 新浪金融;US: Stooq 日线最新价 fallback
"""
from __future__ import annotations
import argparse, json, os, ssl, sys, time, urllib.parse, urllib.request
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "price_watch"
STATE.mkdir(parents=True, exist_ok=True)


def _proxy_opener():
    proxy = os.environ.get("ALL_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    if proxy and proxy.startswith("socks5"):
        try:
            import socks, socket
            host, port = proxy.replace("socks5://", "").split(":")
            socks.set_default_proxy(socks.SOCKS5, host, int(port))
            socket.socket = socks.socksocket
        except Exception:
            pass
    return urllib.request.build_opener()


_OPENER = _proxy_opener()


def _get(url, timeout=10, referer=None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    h = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X) AppleWebKit/605 Chrome/120"}
    if referer: h["Referer"] = referer
    req = urllib.request.Request(url, headers=h)
    with _OPENER.open(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def _sina_symbol(ticker: str) -> str | None:
    """把标准 ticker 转成新浪 hs.
    600519.SS -> sh600519; 000858.SZ -> sz000858; 0700.HK -> hk00700
    """
    t = ticker.upper()
    if t.endswith(".SS"):
        return "sh" + t.split(".")[0]
    if t.endswith(".SZ"):
        return "sz" + t.split(".")[0]
    if t.endswith(".HK"):
        num = t.split(".")[0].zfill(5)
        return "hk" + num
    return None


def quote_a_h(ticker: str) -> float | None:
    sym = _sina_symbol(ticker)
    if not sym: return None
    try:
        txt = _get(f"https://hq.sinajs.cn/list={sym}", referer="https://finance.sina.com.cn/")
        # var hq_str_sh600519="贵州茅台, open, prev_close, current, high, low, ..."
        parts = txt.split('"')[1].split(",")
        if sym.startswith("hk"):
            # hk 格式: name_en, name, open, prev, high, low, current, ...
            return float(parts[6]) if len(parts) > 6 else None
        # A 股 sh/sz 格式: name, open, prev, current, high, low, ...
        return float(parts[3]) if len(parts) > 3 else None
    except Exception as e:
        print(f"[watch] sina 失败 {ticker}: {e}", file=sys.stderr)
        return None


def quote_us(ticker: str) -> float | None:
    """用项目的 market_data._yahoo(经代理+多域名轮询)取最新收盘价。"""
    try:
        from tools.market_data import _yahoo
        import asyncio
        from datetime import date as _date
        bars = asyncio.run(_yahoo(ticker, _date.today(), 3))
        if bars:
            return float(bars[-1].close)
    except Exception:
        pass
    """先 Yahoo v7 quote(备用),失败回退 Stooq。"""
    try:
        txt = _get(f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={ticker}",
                   referer="https://finance.yahoo.com/")
        j = json.loads(txt)
        arr = j.get("quoteResponse", {}).get("result") or []
        if arr:
            p = arr[0].get("regularMarketPrice") or arr[0].get("postMarketPrice")
            if p: return float(p)
    except Exception:
        pass
    for sym in (f"{ticker.lower()}.us", ticker.lower()):
        try:
            txt = _get(f"https://stooq.com/q/l/?s={sym}&f=sd2t2ohlcv&h&e=csv")
            rows = [l for l in txt.splitlines() if l.strip()]
            if len(rows) < 2: continue
            cols = rows[1].split(",")
            if len(cols) > 6 and cols[6] not in ("N/D", ""):
                return float(cols[6])
        except Exception:
            continue
    print(f"[watch] US 报价失败 {ticker}", file=sys.stderr)
    return None


def quote(ticker: str) -> float | None:
    if ticker.upper().endswith((".SS", ".SZ", ".HK")):
        return quote_a_h(ticker)
    return quote_us(ticker)


def snapshot(tickers: list[str]) -> dict[str, float]:
    out = {}
    for t in tickers:
        p = quote(t)
        if p is not None:
            out[t] = p
    return out


def _load_prev() -> dict:
    p = STATE / "last.json"
    if p.exists():
        try: return json.load(open(p))
        except Exception: return {}
    return {}


def _save(snap: dict):
    json.dump({"ts": datetime.now().isoformat(), "prices": snap},
              open(STATE / "last.json", "w"), ensure_ascii=False, indent=2)


def diff_alert(cur: dict, prev: dict, pct_thr: float) -> list[str]:
    alerts = []
    prev_p = prev.get("prices", {})
    for t, p in cur.items():
        p0 = prev_p.get(t)
        if not p0: continue
        change = (p - p0) / p0 * 100
        if abs(change) >= pct_thr:
            alerts.append(f"{t} {p0:.3f}→{p:.3f} ({change:+.2f}%)")
    return alerts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", default="core")
    ap.add_argument("--tickers", help="覆盖 watchlist,逗号分隔")
    ap.add_argument("--pct", type=float, default=3.0, help="百分比阈值(绝对值)")
    ap.add_argument("--interval", type=int, default=60, help="秒;<=0 只跑一次")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--max-loops", type=int, default=0, help="0=无限")
    args = ap.parse_args()

    if args.tickers:
        tickers = [t.strip() for t in args.tickers.split(",")]
    else:
        wl = yaml.safe_load(open(ROOT / "configs" / "watchlist.yaml"))
        tickers = wl["lists"][args.list]["tickers"]

    print(f"[watch] {len(tickers)} 标的,阈值 {args.pct}%,间隔 {args.interval}s")

    loops = 0
    while True:
        prev = _load_prev()
        cur = snapshot(tickers)
        _save(cur)
        alerts = diff_alert(cur, prev, args.pct)
        ts = datetime.now().strftime("%H:%M:%S")
        if alerts:
            print(f"[{ts}] ALERT × {len(alerts)}")
            for a in alerts:
                print("  ", a)
            try:
                from tools.notify import notify
                notify("StockOps 分钟预警", "\n".join(alerts))
            except Exception:
                pass
        else:
            print(f"[{ts}] {len(cur)} 标的报价正常")
        loops += 1
        if args.once or args.interval <= 0 or (args.max_loops and loops >= args.max_loops):
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
