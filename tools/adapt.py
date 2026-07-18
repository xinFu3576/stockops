"""D8+D9 闭环学习:扫已回填 MemoryRecord,按 key_points tag 归因,建议新的分析师权重。

用法:
  python -m tools.adapt --as_of 2026-07-17 --min-samples 20
  # 会输出建议并可选写入 configs/weights.yaml
  python -m tools.adapt --as_of 2026-07-17 --apply

权重被 research_manager 在启动时读一次(若文件存在),否则 fallback 到常量。
"""
from __future__ import annotations
import argparse, json, os, re, sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

from core.schemas import MemoryRecord, Direction
from tools.memory import MEM_DIR


ROOT = Path(__file__).resolve().parents[1]
WEIGHTS_FILE = ROOT / "configs" / "weights.yaml"

DEFAULT_WEIGHTS = {
    "technical": 0.35, "fundamental": 0.30, "sentiment": 0.15, "macro_event": 0.20
}
ANALYSTS = list(DEFAULT_WEIGHTS.keys())
TAG_RE = re.compile(r"\[(fundamental|technical|sentiment|macro_event)\]")


def load_weights() -> dict[str, float]:
    if WEIGHTS_FILE.exists():
        try:
            d = yaml.safe_load(open(WEIGHTS_FILE)) or {}
            w = {k: float(d.get(k, DEFAULT_WEIGHTS[k])) for k in ANALYSTS}
            s = sum(w.values()) or 1.0
            return {k: v / s for k, v in w.items()}
        except Exception:
            pass
    return dict(DEFAULT_WEIGHTS)


def _iter_completed(as_of: date):
    root = os.path.abspath(MEM_DIR)
    if not os.path.isdir(root):
        return
    for tk in sorted(os.listdir(root)):
        dp = os.path.join(root, tk)
        if not os.path.isdir(dp): continue
        for fname in sorted(os.listdir(dp)):
            fp = os.path.join(dp, fname)
            try:
                rec = MemoryRecord.model_validate_json(open(fp).read())
            except Exception:
                continue
            if rec.realized_return is None or rec.alpha_vs_benchmark is None:
                continue
            yield rec


def _direction_sign(d: Direction) -> int:
    if d in (Direction.BUY, Direction.STRONG_BUY): return 1
    if d in (Direction.SELL, Direction.STRONG_SELL): return -1
    return 0


def analyze(as_of: date, min_samples: int) -> dict:
    """按 key_points tag 归因,给每位分析师算 hit_rate 与 avg_alpha。"""
    stat = {a: {"n": 0, "hits": 0, "alpha_sum": 0.0} for a in ANALYSTS}
    total_recs = 0
    for rec in _iter_completed(as_of):
        total_recs += 1
        alpha = rec.alpha_vs_benchmark or 0.0
        sign = _direction_sign(rec.decision.direction)
        strat = rec.realized_return or 0.0
        # 命中定义:方向×收益 > 0(HOLD 视作打平,不入命中/失败但入 alpha 平均)
        if sign == 0:
            hit = None
        else:
            hit = 1 if strat * sign > 0 else 0
        # tag 归因
        tags = set()
        for kp in rec.decision.key_points:
            m = TAG_RE.search(kp)
            if m:
                tags.add(m.group(1))
        if not tags:  # 没 tag,平摊
            tags = set(ANALYSTS)
        for t in tags:
            stat[t]["n"] += 1
            if hit is not None:
                stat[t]["hits"] += hit
            stat[t]["alpha_sum"] += alpha
    summary = {}
    for a, s in stat.items():
        n = s["n"] or 1
        summary[a] = {
            "n": s["n"],
            "hit_rate": (s["hits"] / n) if s["n"] else None,
            "avg_alpha": (s["alpha_sum"] / n) if s["n"] else 0.0,
        }
    return {"total": total_recs, "min_samples": min_samples, "per_analyst": summary}


def suggest_weights(summary: dict) -> dict[str, float]:
    """按 avg_alpha 相对水平做温和调整;样本不足则回退默认。"""
    per = summary["per_analyst"]
    if summary["total"] < summary["min_samples"]:
        return dict(DEFAULT_WEIGHTS)
    scores = {a: max(-0.05, per[a]["avg_alpha"]) for a in ANALYSTS}
    # 转成正数权重
    shift = -min(scores.values()) + 0.01
    raw = {a: (scores[a] + shift) * DEFAULT_WEIGHTS[a] for a in ANALYSTS}
    total = sum(raw.values()) or 1.0
    return {a: round(raw[a] / total, 3) for a in ANALYSTS}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as_of", required=True)
    ap.add_argument("--min-samples", type=int, default=20)
    ap.add_argument("--apply", action="store_true", help="写入 configs/weights.yaml")
    args = ap.parse_args()

    summary = analyze(date.fromisoformat(args.as_of), args.min_samples)
    print(f"完成回填的记录: {summary['total']} (阈值 {summary['min_samples']})")
    print(f"{'分析师':<14}{'n':>5}{'hit':>8}{'α':>10}")
    for a, s in summary["per_analyst"].items():
        hit = f"{s['hit_rate']*100:.1f}%" if s['hit_rate'] is not None else "-"
        print(f"{a:<14}{s['n']:>5}{hit:>8}{s['avg_alpha']*100:>9.2f}%")

    suggested = suggest_weights(summary)
    cur = load_weights()
    print("\n当前权重:", cur)
    print("建议权重:", suggested)

    if args.apply:
        WEIGHTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        yaml.safe_dump(suggested, open(WEIGHTS_FILE, "w"), sort_keys=True)
        print(f"[apply] 写入 {WEIGHTS_FILE}")
    else:
        print("(未写入;加 --apply 生效)")


if __name__ == "__main__":
    main()
