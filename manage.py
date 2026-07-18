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
    sub.add_parser("test").set_defaults(fn=cmd_test)
    sub.add_parser("status").set_defaults(fn=cmd_status)

    args = ap.parse_args()
    return args.fn(args) or 0


if __name__ == "__main__":
    sys.exit(main())
