"""批处理 runner:读 watchlist.yaml,跑 pipeline,对比昨日,触发 alert。
用法: python -m tools.batch_runner --list core --date 2026-07-17
     python -m tools.batch_runner --all --date 2026-07-17 --alert-out reports/alert_YYYYMMDD.md
"""
from __future__ import annotations
import argparse, asyncio, json, os, sys
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from core.orchestrator import run_batch


ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "configs" / "watchlist.yaml"
STATE_DIR = ROOT / "data" / "batch_state"
STATE_DIR.mkdir(parents=True, exist_ok=True)


def load_watchlist():
    return yaml.safe_load(open(CFG))


def state_path(as_of: date) -> Path:
    return STATE_DIR / f"batch_{as_of.isoformat()}.json"


def prev_state(as_of: date, max_look_back: int = 7):
    for i in range(1, max_look_back + 1):
        p = state_path(as_of - timedelta(days=i))
        if p.exists():
            return json.load(open(p)), p.stem
    return None, None


async def _run(tickers, as_of, mode):
    return await run_batch(tickers, as_of, mode, force=True)


def gather_snapshots(result):
    snaps = {}
    for st in result["states"]:
        d = st.decision.model_dump() if st.decision else {}
        snaps[st.ticker] = {
            "direction": d.get("direction"),
            "score": d.get("score"),
            "confidence": d.get("confidence"),
            "risks": d.get("risks", []),
            "risk_status": (st.risk_verdict or {}).get("status") if hasattr(st, "risk_verdict") else None,
        }
    return snaps


def diff_and_alert(cur, prev, cfg):
    thr_s = cfg["alert"]["score_delta_threshold"]
    thr_c = cfg["alert"]["confidence_min"]
    lines = []
    for tic, cs in cur.items():
        ps = (prev or {}).get(tic)
        if not ps:
            lines.append(f"NEW  {tic} dir={cs['direction']} score={cs['score']} conf={cs['confidence']}")
            continue
        ds = (cs["score"] or 0) - (ps["score"] or 0)
        if abs(ds) >= thr_s and (cs["confidence"] or 0) >= thr_c:
            lines.append(
                f"MOVE {tic} score {ps['score']} → {cs['score']} (Δ{ds:+d}), "
                f"dir {ps['direction']}→{cs['direction']}, conf={cs['confidence']}"
            )
        if cfg["alert"].get("risk_block_alert") and (cs.get("risk_status") == "block"):
            lines.append(f"BLOCK {tic} 风控拦截")
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", help="watchlist.yaml 内的 list 名(core/candidates/...)")
    ap.add_argument("--all", action="store_true", help="所有 list 合并")
    ap.add_argument("--date", required=True)
    ap.add_argument("--mode", default="dry_run")
    ap.add_argument("--alert-out", default=None, help="预警文件路径,默认 reports/alert_<date>.md")
    args = ap.parse_args()

    wl = load_watchlist()
    if args.all:
        tickers = sorted({t for L in wl["lists"].values() for t in L["tickers"]})
    else:
        if not args.list:
            sys.exit("必须提供 --list 或 --all")
        tickers = wl["lists"][args.list]["tickers"]

    as_of = date.fromisoformat(args.date)
    print(f"[batch] {len(tickers)} 标的 @ {as_of} mode={args.mode}")
    result = asyncio.run(_run(tickers, as_of, args.mode))
    snaps = gather_snapshots(result)

    # persist today
    json.dump(snaps, open(state_path(as_of), "w"), ensure_ascii=False, indent=2)

    prev, prev_name = prev_state(as_of)
    alerts = diff_and_alert(snaps, prev, wl)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.alert_out) if args.alert_out else ROOT / "reports" / f"alert_{as_of.isoformat()}_{ts}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        f.write(f"# StockOps 日报 · {as_of.isoformat()}\n\n")
        f.write(f"标的: {', '.join(tickers)}\n上一份状态: {prev_name or '(无历史)'}\n\n## 预警\n")
        if alerts:
            for l in alerts:
                f.write(f"- {l}\n")
        else:
            f.write("- 无变化超过阈值\n")
        f.write("\n## 快照\n| 标的 | 方向 | 评分 | 信心 |\n|---|---|---|---|\n")
        for tic, s in snaps.items():
            f.write(f"| {tic} | {s['direction']} | {s['score']} | {s['confidence']} |\n")
        if result["violations"]:
            f.write("\n## 组合违规\n")
            for v in result["violations"]:
                f.write(f"- {v}\n")

    print(f"[batch] wrote {out}")
    for l in alerts:
        print("  ", l)
    if alerts:
        try:
            from tools.notify import notify
            title = f"StockOps 预警 · {as_of.isoformat()}({len(alerts)} 项)"
            body = open(out).read()
            res = notify(title, body)
            if any(res.values()):
                print(f"[notify] 已推送: {res}")
        except Exception as e:
            print(f"[notify] 跳过: {e}")


if __name__ == "__main__":
    main()
