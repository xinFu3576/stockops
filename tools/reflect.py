"""D8 反思闭环：给历史决策回填 realized_return，并生成 reflection。

用法：
  # 回填 N 天前的所有决策
  python -m tools.reflect --horizon 20 --as_of 2026-07-17

  # 只回填某标的
  python -m tools.reflect --ticker 600519.SS --horizon 20 --as_of 2026-07-17
"""
from __future__ import annotations
import argparse, asyncio, os
from datetime import date, datetime, timedelta

from core.schemas import Decision, Direction, MemoryRecord
from tools.market_data import fetch_market_data
from tools.memory import MEM_DIR


DIR_SIGN = {
    Direction.STRONG_BUY: 1.0, Direction.BUY: 0.5, Direction.HOLD: 0.0,
    Direction.SELL: -0.5, Direction.STRONG_SELL: -1.0,
}


async def _realized(dec: Decision, horizon: int) -> tuple[float | None, float | None]:
    """返回 (策略实现收益, 基准同期涨跌)。策略收益 = 方向 sign × 期间涨跌。"""
    end = dec.as_of + timedelta(days=int(horizon * 1.5))  # 拉宽以覆盖非交易日
    try:
        md = await fetch_market_data(dec.ticker, end, lookback=horizon * 2 + 20)
    except Exception:
        return None, None
    bars = [b for b in md.bars if b.date >= dec.as_of]
    if len(bars) < 2:
        return None, None
    entry = bars[0].close
    # 取入场后第 horizon 个交易日 (或最后一个) 作为结算点
    idx = min(horizon, len(bars) - 1)
    exit_p = bars[idx].close
    bench_ret = (exit_p / entry) - 1
    sign = DIR_SIGN.get(dec.direction, 0.0)
    strat_ret = sign * bench_ret
    return round(strat_ret, 4), round(bench_ret, 4)


def _reflect(dec: Decision, strat_ret: float, bench_ret: float) -> str:
    """规则版反思：对错原因归因到分析师层。"""
    sign = DIR_SIGN.get(dec.direction, 0.0)
    if abs(sign) < 0.01:
        return f"HOLD 决策，同期基准 {bench_ret:+.2%}，未参与。"
    correct = strat_ret > 0
    tag = "✅ 正确" if correct else "❌ 错误"
    alpha = strat_ret - (bench_ret if sign > 0 else -bench_ret)
    reasons = []
    for k in dec.key_points[:3]:
        reasons.append(k)
    lesson_bank = {
        "correct_high_conf": "高信心 & 判对，可强化同类信号权重。",
        "correct_low_conf": "低信心但判对，属于运气，无需过度强化。",
        "wrong_high_conf": "高信心却判错 —— 检查是否忽视了对立面证据 / 事件面。",
        "wrong_low_conf": "低信心判错，属于合理试错，注意仓位控制。",
    }
    conf_tag = "high" if dec.confidence >= 0.5 else "low"
    key = f"{'correct' if correct else 'wrong'}_{conf_tag}_conf"
    lesson = lesson_bank[key]
    return (f"{tag} · 策略收益 {strat_ret:+.2%} · 基准 {bench_ret:+.2%} · alpha {alpha:+.2%}\n"
            f"决策论据: {'; '.join(reasons)}\n"
            f"教训: {lesson}")


def _iter_decisions(ticker: str | None, min_age_days: int, as_of: date):
    """遍历磁盘上的决策，只处理 (as_of - decision.as_of) >= min_age_days 且尚未回填的。"""
    root = os.path.abspath(MEM_DIR)
    if not os.path.isdir(root):
        return
    tickers = [ticker] if ticker else sorted(os.listdir(root))
    for tk in tickers:
        dp = os.path.join(root, tk)
        if not os.path.isdir(dp):
            continue
        for fname in sorted(os.listdir(dp)):
            fp = os.path.join(dp, fname)
            try:
                with open(fp) as fh:
                    txt = fh.read().strip()
                if not txt:
                    continue
                rec = MemoryRecord.model_validate_json(txt)
            except Exception:
                continue
            age = (as_of - rec.decision.as_of).days
            if age < min_age_days:
                continue
            if rec.realized_return is not None and rec.reflection:
                continue
            yield fp, rec


async def _one(fp: str, rec: MemoryRecord, horizon: int) -> str:
    strat, bench = await _realized(rec.decision, horizon)
    if strat is None:
        return f"[skip] {rec.decision.ticker}@{rec.decision.as_of} 无数据"
    rec.realized_return = strat
    rec.alpha_vs_benchmark = strat - (bench or 0)
    rec.reflection = _reflect(rec.decision, strat, bench or 0.0)
    with open(fp, "w") as fh:
        fh.write(rec.model_dump_json(indent=2))
    return f"[ok] {rec.decision.ticker}@{rec.decision.as_of} strat={strat:+.2%} bench={bench:+.2%}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default=None)
    ap.add_argument("--horizon", type=int, default=20)
    ap.add_argument("--as_of", required=True)
    args = ap.parse_args()

    as_of = date.fromisoformat(args.as_of)
    items = list(_iter_decisions(args.ticker, args.horizon, as_of))
    if not items:
        print(f"没有需要回填的决策 (as_of={as_of}, horizon={args.horizon})")
        return

    async def _all():
        results = []
        for fp, rec in items:
            results.append(await _one(fp, rec, args.horizon))
        return results

    for line in asyncio.run(_all()):
        print(line)


if __name__ == "__main__":
    main()
