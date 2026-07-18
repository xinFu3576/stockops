"""一体化闭环:reflect(回填 realized) → adapt(重算权重)。
用途:给 stock_reflection 心跳直接调,或作为 daily.sh 的第 4 步。

用法:
  python -m tools.learn --as_of 2026-07-17 --horizon 20 --min-samples 20 --apply
  # --dry-run: 只 reflect + adapt 建议,不写权重
"""
from __future__ import annotations
import argparse, asyncio, subprocess, sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as_of", required=True)
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--min-samples", type=int, default=20)
    ap.add_argument("--apply", action="store_true", help="通过 min-samples 校验后写 weights.yaml")
    ap.add_argument("--dry-run", action="store_true", help="只跑 reflect + adapt,不写")
    args = ap.parse_args()

    print(f"[learn] as_of={args.as_of} horizon={args.horizon}")
    py = sys.executable

    print("-- step 1: reflect --")
    rc, out = _run([py, "-m", "tools.reflect", "--horizon", str(args.horizon), "--as_of", args.as_of])
    print(out.strip() or "(空)")

    print("-- step 2: adapt --")
    cmd = [py, "-m", "tools.adapt", "--as_of", args.as_of, "--min-samples", str(args.min_samples)]
    if args.apply and not args.dry_run:
        cmd.append("--apply")
    rc, out = _run(cmd)
    print(out.strip())

    print("[learn] done")


if __name__ == "__main__":
    main()
