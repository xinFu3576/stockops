"""投研经理 — LLM 优先 + 启发式兜底 + 强一致性校验。

规则：LLM 出的 Decision 必须与启发式方向差异不超过 1 档，否则触发保守化回退。
"""
from __future__ import annotations
from core.schemas import Decision, Direction, AnalystVerdict
from agents_llm.llm_client import client


_DIR_SCORE = {
    Direction.STRONG_BUY: 1.0, Direction.BUY: 0.5, Direction.HOLD: 0.0,
    Direction.SELL: -0.5, Direction.STRONG_SELL: -1.0,
}
try:
    from tools.adapt import load_weights as _load_weights
    _WEIGHTS = _load_weights()
except Exception:
    _WEIGHTS = {"technical": 0.28, "fundamental": 0.24, "sentiment": 0.14, "macro_event": 0.16, "portfolio_view": 0.18}


def _weighted_score(verdicts: dict[str, AnalystVerdict]) -> tuple[float, float]:
    if not verdicts: return 0.0, 0.0
    total_w = 0.0; s = 0.0; conf = 0.0
    for name, v in verdicts.items():
        w = _WEIGHTS.get(name, 0.1) * v.confidence
        s += _DIR_SCORE[v.direction] * w
        conf += v.confidence * _WEIGHTS.get(name, 0.1)
        total_w += _WEIGHTS.get(name, 0.1)
    return s / total_w if total_w else 0.0, conf / total_w if total_w else 0.0


def _score_to_direction(score: float) -> Direction:
    if score >= 0.55: return Direction.STRONG_BUY
    if score >= 0.15: return Direction.BUY
    if score <= -0.55: return Direction.STRONG_SELL
    if score <= -0.15: return Direction.SELL
    return Direction.HOLD


def _stop_take(direction: Direction, entry: float | None, atr: float | None) -> tuple[float | None, float | None]:
    if entry is None: return None, None
    band = atr * 2 if atr else entry * 0.05
    if direction in (Direction.BUY, Direction.STRONG_BUY):
        return round(entry - band, 3), round(entry + band * 2, 3)
    if direction in (Direction.SELL, Direction.STRONG_SELL):
        return round(entry + band, 3), round(entry - band * 2, 3)
    # HOLD：给参考止损止盈 (±band)
    return round(entry - band, 3), round(entry + band, 3)


def _entry_and_atr(state) -> tuple[float | None, float | None]:
    entry = state.market_data.bars[-1].close if state.market_data and state.market_data.bars else None
    atr = None
    if state.factor_bundle:
        for f in state.factor_bundle.factors:
            if f.name == "atr_14": atr = f.value; break
    return entry, atr


def _heuristic(state) -> Decision:
    score, conf = _weighted_score(state.verdicts)
    direction = _score_to_direction(score)
    key_points: list[str] = []; risks: list[str] = []; catalysts: list[str] = []
    for name, v in state.verdicts.items():
        for p in v.key_points[:2]: key_points.append(f"[{name}] {p}")
        for r in v.risks[:1]: risks.append(f"[{name}] {r}")
        for c in v.catalysts: catalysts.append(c)
    used_mem: list[str] = []
    if state.memory_refs:
        for m in state.memory_refs[-3:]:
            if m.reflection:
                risks.append(f"[记忆] {m.reflection[:60]}")
            used_mem.append(f"{m.decision.ticker}@{m.decision.as_of}")
    risks.append("模型未覆盖极端事件（黑天鹅/停牌/退市）")
    risks.append("数据延迟或缺失可能导致信号失真")
    # v0.8.0 sentiment closed loop: 注入投资情报聚合
    try:
        from tools.investment_news import load_latest, aggregate_sentiment
        _snap = load_latest()
        if _snap:
            _news_items = _snap.get("items", [])
            _agg = aggregate_sentiment(_news_items, tickers=[state.ticker])
            _tk_agg = _agg.get(state.ticker.upper()) or _agg.get("_MARKET")
            if _tk_agg:
                lbl = _tk_agg.get("label", "neutral")
                avg = _tk_agg.get("avg", 0.0)
                n = _tk_agg.get("count", 0)
                if lbl == "negative" and avg < -0.3:
                    risks.append(f"[情报] 全网负面情绪 avg={avg} (n={n})，警惕舆情/监管风险")
                elif lbl == "positive" and avg > 0.3:
                    key_points.append(f"[情报] 全网正面情绪 avg={avg} (n={n})，短线情绪支撑")
                else:
                    key_points.append(f"[情报] 情绪中性 avg={avg} (n={n})")
                # top 3 headline 提供证据；正面 → catalysts, 负面 → risks
                _tk_items = [it for it in _news_items if state.ticker.upper() in [t.upper() for t in it.get("tickers",[])]]
                for it in sorted(_tk_items, key=lambda x: -abs(x.get("sentiment_score",0)))[:3]:
                    _lbl = it.get("sentiment_label","?")
                    _score = it.get("sentiment_score", 0)
                    _title = it.get("title","")[:80]
                    _src = it.get("source","?")
                    if _score > 0.3:
                        catalysts.append(f"[{_src}/正面 {_score:+.2f}] {_title}")
                    elif _score < -0.3:
                        risks.append(f"[{_src}/负面 {_score:+.2f}] {_title}")
                    else:
                        key_points.append(f"[{_src}/{_lbl}] {_title}")
    except Exception as _e:
        pass
    entry, atr = _entry_and_atr(state)
    stop, take = _stop_take(direction, entry, atr)
    score_100 = max(0, min(100, int(round(50 + score * 50))))
    return Decision(
        ticker=state.ticker, as_of=state.as_of, direction=direction,
        score=score_100, confidence=round(min(0.95, max(0.05, conf)), 2),
        entry_price=entry, stop_loss=stop, take_profit=take, horizon_days=20,
        key_points=key_points[:8], risks=risks[:8],
        catalysts=list(dict.fromkeys(catalysts))[:6],
        checklist=[
            "确认当日为交易日 & 未停牌",
            "确认下单前风控三层通过",
            "确认成本+滑点+印花税已纳入回测口径",
            "确认存在明确止损/止盈价位",
        ],
        used_analysts=list(state.verdicts.keys()),
        used_memory_refs=used_mem,
    )


def _reconcile(llm_dec: Decision, heur_dec: Decision) -> Decision:
    """一致性校验：方向不能与启发式相差 >=2 档，否则强制中性并降信心。"""
    order = [Direction.STRONG_SELL, Direction.SELL, Direction.HOLD, Direction.BUY, Direction.STRONG_BUY]
    gap = abs(order.index(llm_dec.direction) - order.index(heur_dec.direction))
    if gap >= 2:
        llm_dec.direction = Direction.HOLD
        llm_dec.score = 50
        llm_dec.confidence = min(llm_dec.confidence, 0.35)
        llm_dec.risks = [f"LLM 与启发式方向差 {gap} 档，已强制中性化"] + llm_dec.risks
    # 保证 risks 非空
    if not llm_dec.risks:
        llm_dec.risks = heur_dec.risks
    # 补价格 / 止损（LLM 常常填 null）
    if llm_dec.entry_price is None: llm_dec.entry_price = heur_dec.entry_price
    if llm_dec.stop_loss is None: llm_dec.stop_loss = heur_dec.stop_loss
    if llm_dec.take_profit is None: llm_dec.take_profit = heur_dec.take_profit
    if not llm_dec.checklist: llm_dec.checklist = heur_dec.checklist
    if not llm_dec.used_analysts: llm_dec.used_analysts = heur_dec.used_analysts
    return llm_dec


def _render(state, heur: Decision) -> str:
    parts = [f"标的={state.ticker} 日期={state.as_of}"]
    parts.append(f"启发式预设方向={heur.direction} 分数={heur.score} 信心={heur.confidence}")
    for name, v in state.verdicts.items():
        parts.append(f"[{name}] 方向={v.direction} 信心={v.confidence} key={v.key_points[:2]}")
    for t in state.debate[-4:]:
        parts.append(f"[{t.side} r{t.round}] {t.argument[:200]}")
    if state.memory_refs:
        parts.append("历史决策与教训：")
        for m in state.memory_refs[-3:]:
            parts.append(f"- {m.decision.as_of} 方向={m.decision.direction} 实现={m.realized_return} 复盘={m.reflection or '—'}")
    return "\n".join(parts)


async def decide(state) -> Decision:
    heur = _heuristic(state)
    if not client.enabled:
        return heur
    sys = (
        "你是资深投研经理。综合 4 位分析师报告 + 多空辩论 + 历史决策，输出结构化 Decision。"
        "严格要求：risks ≥ 3 条；score(0-100) 必须与 direction 一致；"
        "如无充足证据 → HOLD；不要虚构催化剂。"
    )
    dec = await client.structured("deep", sys, _render(state, heur), Decision)
    if dec is None:
        return heur
    dec.ticker = state.ticker
    dec.as_of = state.as_of
    return _reconcile(dec, heur)
