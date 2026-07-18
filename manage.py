#!/usr/bin/env python3
"""StockOps 统一入口:一行调 CLI/heartbeat/复盘/学习/健康检查。

  ./manage.py daily [--date YYYY-MM-DD]      # 一键日跑
  ./manage.py decide AAPL,600519.SS          # 单次决策
  ./manage.py verify                         # 健康报告
  ./manage.py backtest AAPL --lookback 500
  ./manage.py grid AAPL,600519.SS
  ./manage.py learn --as_of 2026-07-17       # reflect + adapt
  ./manage.py adapt --as_of 2026-07-17 --apply
  ./manage.py watch AAPL,NVDA --pct 3 --once
  ./manage.py paper-status                   # 打印 paper 账户
  ./manage.py paper-reset
  ./manage.py test                           # pytest
  ./manage.py status                         # 打印团队装备清单
"""
import argparse, json, os, subprocess, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv" / "bin" / "python"
PY = str(VENV) if VENV.exists() else sys.executable


def _run(*args):
    return subprocess.call([PY, *args])


def cmd_daily(a):
    d = a.date or date.today().isoformat()
    return subprocess.call([str(ROOT / "daily.sh"), d])


def cmd_decide(a):
    return _run("-m", "core.orchestrator", "--tickers", a.tickers,
                "--date", a.date or date.today().isoformat(),
                "--mode", a.mode, "--force",
                *(["--i-accept-real-money"] if a.i_accept_real_money else []))


def cmd_verify(a):
    return _run("-m", "tools.verify", "--tickers", a.tickers,
                "--date", a.date or date.today().isoformat())


def cmd_backtest(a):
    return _run("-m", "tools.backtest_cli", "--tickers", a.tickers,
                "--date", a.date or date.today().isoformat(),
                "--lookback", str(a.lookback))


def cmd_grid(a):
    return _run("-m", "tools.grid_search", "--tickers", a.tickers,
                "--date", a.date or date.today().isoformat(),
                "--top", str(a.top))


def cmd_learn(a):
    args = ["-m", "tools.learn", "--as_of", a.as_of, "--horizon", str(a.horizon),
            "--min-samples", str(a.min_samples)]
    if a.apply: args.append("--apply")
    return _run(*args)


def cmd_adapt(a):
    args = ["-m", "tools.adapt", "--as_of", a.as_of, "--min-samples", str(a.min_samples)]
    if a.apply: args.append("--apply")
    return _run(*args)


def cmd_watch(a):
    args = ["-m", "tools.price_watch", "--pct", str(a.pct)]
    if a.tickers: args += ["--tickers", a.tickers]
    else: args += ["--list", a.list]
    if a.once: args.append("--once")
    else: args += ["--interval", str(a.interval)]
    return _run(*args)


def cmd_paper_status(a):
    p = ROOT / "data" / "paper" / "account.json"
    if not p.exists():
        print("(未持仓)")
        return 0
    print(json.dumps(json.load(open(p)), indent=2, ensure_ascii=False))
    return 0


def cmd_paper_reset(a):
    for f in ("account.json", "ledger.json"):
        p = ROOT / "data" / "paper" / f
        if p.exists(): p.unlink()
    print("[paper] reset")
    return 0



def cmd_broker_health(a):
    import asyncio, json
    from tools.brokers import get_broker
    from tools.options_chain import health as opt_health
    names = a.brokers.split(",") if a.brokers else ["dry_run","paper","ibkr","futu"]
    async def _run():
        for n in names:
            b = get_broker(n.strip())
            h = await b.health() if hasattr(b, "health") else {"ok": True, "reason": "no health() method"}
            print(f"{n:>10s}: {json.dumps(h, ensure_ascii=False)}")
    asyncio.run(_run())
    print(f"\n[options] 数据源: {json.dumps(opt_health(), ensure_ascii=False)}")
    return 0



def cmd_news(a):
    args = ["-m", "tools.investment_news", "--top", str(a.top)]
    if a.sources: args += ["--sources", a.sources]
    if a.keywords: args += ["--keywords", a.keywords]
    if a.tickers: args += ["--tickers", a.tickers]
    if a.save: args += ["--save"]
    if a.notify: args += ["--notify"]
    return _run(*args)


def cmd_dashboard(a):
    return _run("-m", "dashboard.server", "--port", str(a.port))


def cmd_test(a):
    return _run("-m", "pytest", "tests/", "-v")


def cmd_status(a):
    print("StockOps 状态\n")
    print(f"项目: {ROOT}")
    print(f"venv: {'✓' if VENV.exists() else '✗ 未创建,请 python -m venv .venv'}")
    weights = ROOT / "configs" / "weights.yaml"
    print(f"权重文件: {'✓ 已学习' if weights.exists() else '(未学习,用默认)'}")
    paper = ROOT / "data" / "paper" / "account.json"
    print(f"paper 账户: {'✓ 有持仓' if paper.exists() else '(空)'}")
    mem = ROOT / "data" / "memory"
    n_mem = sum(len(os.listdir(mem / d)) for d in os.listdir(mem)
                if (mem / d).is_dir()) if mem.exists() else 0
    print(f"决策记忆: {n_mem} 条")
    reports = ROOT / "reports"
    n_rpt = len(list(reports.glob("*.md"))) if reports.exists() else 0
    print(f"历史报告: {n_rpt} 份")
    return 0




def cmd_rebalance(a):
    """演示模式:根据现有 memory 决策 + 当前持仓生成 rebalance orders。"""
    import json, pathlib
    from datetime import date, timedelta
    from tools.memory import iter_records
    from tools.rebalance import Position, compute_target_weights, build_rebalance_plan
    from core.schemas import Direction

    # 用最近 N 天最新决策
    since = date.today() - timedelta(days=a.days)
    latest = {}
    for r in iter_records():
        dec = r.get("decision") or {}
        tk = dec.get("ticker"); as_of = dec.get("as_of")
        if not tk or not as_of: continue
        d = as_of if hasattr(as_of, "isoformat") else as_of
        if isinstance(d, str):
            from datetime import datetime as _dt
            d = _dt.fromisoformat(d[:10]).date()
        if d < since: continue
        if tk not in latest or d > latest[tk][0]:
            from core.schemas import Decision as _D
            try:
                latest[tk] = (d, _D(**dec))
            except Exception:
                pass
    decisions = {tk: rec[1] for tk, rec in latest.items()}
    if not decisions:
        print(f"[rebalance] 近 {a.days} 天无决策记录")
        return 0
    weights = compute_target_weights(decisions, method=a.method,
                                     max_single=a.max_single, cash_floor=a.cash_floor)
    print(f"[rebalance] 目标权重 ({a.method}):")
    for tk, w in sorted(weights.items(), key=lambda x: -abs(x[1])):
        print(f"  {tk:>12s}: {w:+.2%}")

    if a.positions and pathlib.Path(a.positions).exists():
        pos_raw = json.loads(pathlib.Path(a.positions).read_text())
        positions = {p["ticker"]: Position(**p) for p in pos_raw}
    elif getattr(a, "execute", None):
        # v0.10.0：--execute 时从 broker 直接拉 positions
        import asyncio
        from tools.brokers import get_broker
        try:
            _b = get_broker(a.execute)
            _pos = asyncio.run(_b.positions())
            positions = {tk: Position(ticker=tk, qty=int(v.get("qty",0)),
                                       avg_cost=float(v.get("avg_price",0)),
                                       market_price=float(v.get("last",0) or v.get("avg_price",0)))
                          for tk, v in _pos.items() if int(v.get("qty",0)) != 0}
            print(f"[rebalance] 从 {a.execute} broker 拉到 {len(positions)} 持仓")
        except Exception as e:
            print(f"[rebalance] broker positions 拉取失败: {e}")
            positions = {}
    else:
        positions = {}
    if a.prices and pathlib.Path(a.prices).exists():
        prices = json.loads(pathlib.Path(a.prices).read_text())
    else:
        prices = {tk: (p.market_price or p.avg_cost) for tk, p in positions.items()}

    plan = build_rebalance_plan(weights, positions, prices, a.equity, a.tolerance)
    print(f"\n[rebalance] orders ({len(plan.orders)}):")
    for o in plan.orders:
        print(f"  {o.side:>4s} {o.ticker:>12s} qty={o.qty:>6d} @ {o.price}  [{o.tag}]")
    print(f"\n[rebalance] reasons ({len(plan.reasons)}):")
    for r in plan.reasons: print(f"  - {r}")

    # v0.10.0: 联动 broker 直接下单
    if getattr(a, "execute", None) and plan.orders:
        import asyncio
        from tools.brokers import get_broker
        broker = get_broker(a.execute)
        print(f"\n[rebalance] 通过 broker={a.execute} 执行 {len(plan.orders)} 单...")
        async def _run():
            for o in plan.orders:
                res = await broker.place_order(o)
                fp = res.filled_price if res.filled_price else o.price
                print(f"  [{res.status}] {o.side} {o.ticker} qty={o.qty} @ {fp} → order_id={res.order_id} {res.reason}")
        asyncio.run(_run())
    return 0


def cmd_options_skew(a):
    from tools.options_chain import fetch_options_skew, health
    print(f"[options] 数据源健康: {health()}")
    for tk in (a.tickers.split(",") if a.tickers else ["AAPL","TSLA","SPY"]):
        r = fetch_options_skew(tk.strip())
        if r:
            print(f"  {tk:>8s} [{r.source}] skew={r.iv_skew:+.4f if r.iv_skew else 'None'}  "
                  f"pc_ratio={r.put_call_ratio}  spot={r.spot}  n={r.n_contracts}")
        else:
            print(f"  {tk:>8s} 无 API key，将退回 proxy")
    return 0


def cmd_ab(a):
    import json, urllib.request
    # 直接调用 dashboard 端点，或本地重放
    from urllib.parse import urlencode
    from dashboard.server import _ab_sync
    params = {}
    if a.a: params["a"] = [a.a]
    if a.b: params["b"] = [a.b]
    params["days"] = [str(a.days)]
    r = _ab_sync(params)
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    return 0

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("daily"); p.add_argument("--date"); p.set_defaults(fn=cmd_daily)

    p = sub.add_parser("decide")
    p.add_argument("tickers"); p.add_argument("--date")
    p.add_argument("--mode", default="dry_run", choices=["dry_run","paper","live","ibkr","futu"])
    p.add_argument("--i-accept-real-money", action="store_true")
    p.set_defaults(fn=cmd_decide)

    p = sub.add_parser("verify")
    p.add_argument("tickers", nargs="?", default="600519.SS,AAPL,000858.SZ")
    p.add_argument("--date")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("backtest")
    p.add_argument("tickers"); p.add_argument("--date"); p.add_argument("--lookback", type=int, default=500)
    p.set_defaults(fn=cmd_backtest)

    p = sub.add_parser("grid")
    p.add_argument("tickers"); p.add_argument("--date"); p.add_argument("--top", type=int, default=10)
    p.set_defaults(fn=cmd_grid)

    p = sub.add_parser("learn")
    p.add_argument("--as_of", default=date.today().isoformat())
    p.add_argument("--horizon", type=int, default=20)
    p.add_argument("--min-samples", type=int, default=20)
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_learn)

    p = sub.add_parser("adapt")
    p.add_argument("--as_of", default=date.today().isoformat())
    p.add_argument("--min-samples", type=int, default=20)
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_adapt)

    p = sub.add_parser("watch")
    p.add_argument("tickers", nargs="?")
    p.add_argument("--list", default="core"); p.add_argument("--pct", type=float, default=3)
    p.add_argument("--interval", type=int, default=60); p.add_argument("--once", action="store_true")
    p.set_defaults(fn=cmd_watch)

    sub.add_parser("paper-status").set_defaults(fn=cmd_paper_status)
    sub.add_parser("paper-reset").set_defaults(fn=cmd_paper_reset)
    p = sub.add_parser("dashboard"); p.add_argument("--port", type=int, default=8765); p.set_defaults(fn=cmd_dashboard)
    p = sub.add_parser("broker-health"); p.add_argument("--brokers", default="dry_run,paper,ibkr,futu"); p.set_defaults(fn=cmd_broker_health)
    p = sub.add_parser("investment-news"); p.add_argument("--sources"); p.add_argument("--keywords"); p.add_argument("--tickers"); p.add_argument("--top",type=int,default=30); p.add_argument("--save",action="store_true"); p.add_argument("--notify",action="store_true"); p.set_defaults(fn=cmd_news)
    p = sub.add_parser("rebalance")
    p.add_argument("--method", default="kelly", choices=["kelly","equal","risk_parity"])
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--max-single", dest="max_single", type=float, default=0.20)
    p.add_argument("--cash-floor", dest="cash_floor", type=float, default=0.10)
    p.add_argument("--equity", type=float, default=100000.0)
    p.add_argument("--tolerance", type=float, default=0.05)
    p.add_argument("--positions", help="JSON 文件路径 [{ticker, qty, avg_cost, market_price}]")
    p.add_argument("--prices", help="JSON 文件路径 {ticker: price}")
    p.add_argument("--execute", choices=["dry_run","paper","ibkr","futu"], help="直接下单到 broker (可选)")
    p.set_defaults(fn=cmd_rebalance)
    p = sub.add_parser("options-skew"); p.add_argument("--tickers"); p.set_defaults(fn=cmd_options_skew)
    p = sub.add_parser("ab"); p.add_argument("--a"); p.add_argument("--b"); p.add_argument("--days", type=int, default=60); p.set_defaults(fn=cmd_ab)
    sub.add_parser("test").set_defaults(fn=cmd_test)
    sub.add_parser("status").set_defaults(fn=cmd_status)

    args = ap.parse_args()
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
