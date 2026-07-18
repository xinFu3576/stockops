"""Bull vs Bear 辩论 — LLM 优先 + 启发式兜底."""
from __future__ import annotations
from core.schemas import DebateTurn, Direction
from agents_llm.llm_client import client

_BULL = {Direction.STRONG_BUY, Direction.BUY}
_BEAR = {Direction.STRONG_SELL, Direction.SELL}


def _heuristic(state, side: str, r: int, prior: list[DebateTurn]) -> DebateTurn:
    args: list[str] = []; refs: list[str] = []
    for name, v in state.verdicts.items():
        agree = (side == "bull" and v.direction in _BULL) or (side == "bear" and v.direction in _BEAR)
        if agree:
            for p in v.key_points[:2]:
                args.append(f"[{name}] {p}")
            refs.append(name)
        else:
            for rk in v.risks[:1]:
                if side == "bear" and v.direction in _BULL:
                    args.append(f"反方指出 [{name}] 风险: {rk}")
                elif side == "bull" and v.direction in _BEAR:
                    args.append(f"我方认为 [{name}] 的 {rk} 已 price-in")
    if not args:
        args.append("无明确" + ("多头" if side == "bull" else "空头") + "证据，观望")
    if prior:
        args.append(f"回应 {prior[-1].side}: {prior[-1].argument[:80]}")
    return DebateTurn(side=side, round=r, argument=("；".join(args))[:800], references_verdicts=refs)


def _render(state, prior) -> str:
    lines = []
    for name, v in state.verdicts.items():
        lines.append(f"[{name}] 方向={v.direction} 信心={v.confidence} key={v.key_points[:2]} risk={v.risks[:1]}")
    for t in prior[-4:]:
        lines.append(f"[{t.side} r{t.round}] {t.argument[:200]}")
    return "\n".join(lines)


async def run(state, max_rounds: int = 2) -> list[DebateTurn]:
    turns: list[DebateTurn] = []
    for r in range(1, max_rounds + 1):
        for side in ("bull", "bear"):
            v = None
            if client.enabled:
                sys = f"你是{'做多' if side == 'bull' else '做空'}方研究员。基于 4 位分析师的报告与已有辩论，做点对点回应，200-400 字。argument 只能用报告里的事实。references_verdicts 只填 fundamental/technical/sentiment/macro_event。"
                v = await client.structured("deep", sys, _render(state, turns), DebateTurn)
                if v is not None:
                    v.side = side; v.round = r
            if v is None:
                v = _heuristic(state, side, r, turns)
            turns.append(v)
    return turns



def compute_conflict_score(state) -> dict:
    """量化 5 位分析师之间的方向分歧。

    - variance：各 analyst score 的方差（0.0-1.0）
    - dir_disagreement：多空分裂 (bull_count / total 距 0.5 的距离)
    - conflict_score：合并指标 [0-100]，>50 表示强烈分歧
    """
    if not state.verdicts:
        return {"variance": 0.0, "dir_disagreement": 0.0, "conflict_score": 0}
    def _derive_score(v):
        if hasattr(v, "score") and getattr(v, "score", None) is not None:
            return float(v.score)
        _map = {Direction.STRONG_BUY: 1.0, Direction.BUY: 0.5,
                Direction.HOLD: 0.0,
                Direction.SELL: -0.5, Direction.STRONG_SELL: -1.0}
        return _map.get(v.direction, 0.0) * float(getattr(v, "confidence", 1.0))
    scores = [_derive_score(v) for v in state.verdicts.values()]
    n = len(scores)
    mean = sum(scores) / n
    variance = sum((s - mean) ** 2 for s in scores) / n
    bulls = sum(1 for v in state.verdicts.values() if v.direction in _BULL)
    bears = sum(1 for v in state.verdicts.values() if v.direction in _BEAR)
    total = max(1, n)
    # 距离 50/50 越近分歧越大
    dir_disagreement = 1.0 - abs((bulls - bears) / total)
    conflict = min(100, int(round(100 * (0.6 * min(1.0, variance / 0.15) + 0.4 * dir_disagreement))))
    return {"variance": round(variance, 4),
            "dir_disagreement": round(dir_disagreement, 3),
            "conflict_score": conflict,
            "bulls": bulls, "bears": bears, "holds": n - bulls - bears,
            "score_mean": round(mean, 3)}


def synthesize_debate(turns: list[DebateTurn], conflict: dict) -> dict:
    """把辩论摘要 + 冲突分打包给 research_manager."""
    bull_turns = [t for t in turns if t.side == "bull"]
    bear_turns = [t for t in turns if t.side == "bear"]
    return {
        "conflict": conflict,
        "bull_summary": "; ".join(t.argument[:120] for t in bull_turns[-2:]),
        "bear_summary": "; ".join(t.argument[:120] for t in bear_turns[-2:]),
        "n_rounds": max((t.round for t in turns), default=0),
        "high_conflict": conflict.get("conflict_score", 0) >= 60,
    }
