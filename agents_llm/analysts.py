"""4 位分析师 — LLM 优先 + 启发式兜底。"""
from __future__ import annotations
from core.schemas import AnalystVerdict, Direction
from agents_llm.llm_client import client


def _factor_map(state) -> dict[str, float]:
    if not state.factor_bundle: return {}
    return {f.name: f.value for f in state.factor_bundle.factors}


def _score_to_direction(score: float) -> Direction:
    if score >= 0.6: return Direction.STRONG_BUY
    if score >= 0.2: return Direction.BUY
    if score <= -0.6: return Direction.STRONG_SELL
    if score <= -0.2: return Direction.SELL
    return Direction.HOLD


# ---------- Heuristic (兜底 + 事实核对) ----------
def _heuristic_technical(state) -> AnalystVerdict:
    f = _factor_map(state)
    pts: list[str] = []; risks: list[str] = []; s = 0.0
    ma_up = f.get("ma5_over_ma20", 0.0); ma_slow = f.get("ma20_over_ma60", 0.0)
    if ma_up > 0.02: s += 0.25; pts.append(f"MA5/MA20={ma_up:+.2%} 短期上翘")
    elif ma_up < -0.02: s -= 0.25; pts.append(f"MA5/MA20={ma_up:+.2%} 短期下压")
    if ma_slow > 0.01: s += 0.15
    elif ma_slow < -0.01: s -= 0.2; pts.append(f"MA20/MA60={ma_slow:+.2%} 中期下行")
    rsi = f.get("rsi_14", 50.0)
    if rsi > 75: risks.append(f"RSI={rsi:.1f} 超买"); s -= 0.15
    elif rsi < 25: pts.append(f"RSI={rsi:.1f} 超卖"); s += 0.15
    hist = f.get("macd_hist", 0.0); s += 0.1 if hist > 0 else -0.1
    boll = f.get("boll_pos", 0.0)
    if boll > 0.9: risks.append("逼近布林上轨"); s -= 0.1
    elif boll < -0.9: pts.append("贴布林下轨"); s += 0.1
    pos52 = f.get("pct_of_52w_range", 0.5)
    if pos52 > 0.9: risks.append(f"接近 52 周高位 {pos52:.0%}")
    elif pos52 < 0.1: pts.append(f"52 周低位 {pos52:.0%}"); s += 0.1
    vr = f.get("vol_ratio_5_20", 1.0)
    if vr > 1.5 and ma_up > 0: s += 0.1; pts.append(f"放量上攻 量比 {vr:.2f}")
    elif vr > 1.5 and ma_up < 0: risks.append(f"放量下跌 量比 {vr:.2f}"); s -= 0.1
    if not risks: risks.append("技术面无显著风险，需与基本面互证")
    s = max(-1.0, min(1.0, s))
    return AnalystVerdict(analyst="technical", direction=_score_to_direction(s),
        confidence=round(0.4 + min(0.4, abs(s) * 0.5), 2),
        key_points=pts or ["技术信号中性"], risks=risks, horizon_days=20)


def _heuristic_fundamental(state) -> AnalystVerdict:
    f = _factor_map(state); pts: list[str] = []; risks: list[str] = []
    s = 0.0
    has_fund = any(k.startswith("fund_") for k in f)
    if has_fund:
        roe = f.get("fund_roe_weighted", 0)
        gm = f.get("fund_gross_margin", 0)
        rev_yoy = f.get("fund_revenue_yoy", 0)
        np_yoy = f.get("fund_netprofit_yoy", 0)
        eps = f.get("fund_eps", 0)

        if roe > 15: s += 0.25; pts.append(f"加权 ROE {roe:.1f}% 高盈利质量")
        elif roe > 8: s += 0.1; pts.append(f"加权 ROE {roe:.1f}%")
        elif 0 < roe < 5: s -= 0.1; risks.append(f"ROE {roe:.1f}% 偏低")
        elif roe <= 0: s -= 0.3; risks.append("ROE 为负，警惕经营恶化")

        if gm > 40: pts.append(f"毛利率 {gm:.1f}% 具备护城河")
        elif gm and gm < 15: risks.append(f"毛利率仅 {gm:.1f}% 竞争激烈")

        if np_yoy > 30: s += 0.25; pts.append(f"净利同比 {np_yoy:+.1f}% 高增速")
        elif np_yoy > 10: s += 0.15; pts.append(f"净利同比 {np_yoy:+.1f}%")
        elif np_yoy < -20: s -= 0.25; risks.append(f"净利同比 {np_yoy:+.1f}% 大幅下滑")
        elif np_yoy < 0: s -= 0.1; risks.append(f"净利同比 {np_yoy:+.1f}% 承压")

        if rev_yoy > 20: s += 0.1
        elif rev_yoy < -5: s -= 0.1; risks.append(f"营收同比 {rev_yoy:+.1f}% 下滑")

        if eps > 0:
            pts.append(f"EPS {eps:.2f}")

        if not risks:
            risks.append("财务面暂无显著风险，仍需跟踪行业景气")
    else:
        pts.append("非 A 股或无 F10 数据，以价格趋势代理")
        risks.append("未接入财报数据")
        ret20 = f.get("ret_20d", 0.0)
        if ret20 > 0.1: s += 0.15; pts.append(f"20 日涨幅 {ret20:+.1%}")
        elif ret20 < -0.1: s -= 0.15; pts.append(f"20 日跌幅 {ret20:+.1%}")

    s = max(-1.0, min(1.0, s))
    conf = (0.55 if has_fund else 0.3) + min(0.3, abs(s) * 0.4)
    return AnalystVerdict(analyst="fundamental", direction=_score_to_direction(s),
        confidence=round(min(0.9, conf), 2),
        key_points=pts or ["数据不足"],
        risks=risks, catalysts=["财报窗口", "行业景气度"], horizon_days=60)


def _heuristic_sentiment(state) -> AnalystVerdict:
    pts: list[str] = []; risks: list[str] = []; s = 0.0
    if state.sentiment_signal:
        sig = state.sentiment_signal; s = float(sig.score)
        pts.append(f"舆情 {sig.score:+.2f} 覆盖 {sig.volume} 条")
        if sig.top_topics: pts.append("主要话题: " + ", ".join(sig.top_topics[:3]))
        if abs(sig.score) > 0.7: risks.append("情绪极端，警惕反转")
    else:
        pts.append("暂未接入新闻源，情绪中性"); risks.append("情绪层缺失")

    # v0.10.0：options-implied 情绪（真 IV skew + P/C ratio），三级降级
    try:
        from tools.options_chain import fetch_options_skew
        opt = fetch_options_skew(state.ticker)
        if opt and (opt.iv_skew is not None or opt.put_call_ratio is not None):
            if opt.iv_skew is not None:
                # skew = put_iv - call_iv > 0 → 恐慌溢价（下跌保护贵）
                skew = opt.iv_skew
                pts.append(f"[options/{opt.source}] IV skew={skew:+.4f}")
                s += max(-0.3, min(0.3, -skew * 3))  # skew↑ → 情绪↓
                if abs(skew) > 0.08:
                    risks.append(f"IV skew 极值 {skew:+.3f}，隐含事件风险")
            if opt.put_call_ratio is not None:
                pcr = opt.put_call_ratio
                pts.append(f"[options] P/C ratio={pcr:.2f}")
                # pcr > 1.2 = 空头拥挤，反向 → 加分；pcr < 0.6 = 多头拥挤，减分
                if pcr > 1.5: s += 0.1
                elif pcr < 0.5: s -= 0.1
    except Exception:
        pass

    return AnalystVerdict(analyst="sentiment", direction=_score_to_direction(s),
        confidence=0.3 + min(0.3, abs(s) * 0.4),
        key_points=pts, risks=risks or ["情绪指标滞后于价格"], horizon_days=5)


def _heuristic_macro_event(state) -> AnalystVerdict:
    pts: list[str] = []; risks: list[str] = []; s = 0.0
    if state.alt_signals:
        alt = state.alt_signals
        if alt.limit_up_reason: pts.append(f"事件驱动: {alt.limit_up_reason}"); s += 0.2
        if alt.lhb_net_buy:
            net = float(alt.lhb_net_buy)
            if net > 0: s += 0.15; pts.append(f"龙虎榜净买 {net:,.0f}")
            else: s -= 0.15; pts.append(f"龙虎榜净卖 {net:,.0f}")
        if alt.macro_regime:
            pts.append(f"宏观 regime: {alt.macro_regime}")
            r = alt.macro_regime.lower()
            if "risk_off" in r: s -= 0.2; risks.append("宏观 risk-off")
            if "risk_on" in r: s += 0.1
    if not pts: pts.append("暂未接入宏观/资金面，事件面中性")
    if not risks: risks.append("宏观数据缺失，关注 CPI/PPI/PMI")
    return AnalystVerdict(analyst="macro_event", direction=_score_to_direction(s),
        confidence=0.35, key_points=pts, risks=risks,
        catalysts=["CPI/PPI", "美联储议息", "板块政策"], horizon_days=10)


def _heuristic_portfolio_view(state) -> AnalystVerdict:
    """综合视角：options IV skew + 微结构 + 情感 + 因子 → 融合信号。作为第 5 位量化分析师。"""
    f = _factor_map(state)
    pts: list[str] = []; risks: list[str] = []; catalysts: list[str] = []; s = 0.0
    # options IV skew（>0 看跌保护偏贵，市场对下行担忧；<0 看涨溢价，情绪偏亢奋）
    iv_skew = f.get("iv_skew_25d")
    if iv_skew is not None:
        if iv_skew > 0.05:
            s -= 0.15; risks.append(f"[options] IV skew={iv_skew:+.4f} 显著下行担忧")
        elif iv_skew < -0.05:
            s += 0.10; pts.append(f"[options] IV skew={iv_skew:+.4f} 情绪偏亢奋（反向注意）")
            risks.append("[options] 期权情绪亢奋反过来是短线过热信号")
        else:
            pts.append(f"[options] IV skew={iv_skew:+.4f} 中性")
    pc = f.get("put_call_ratio")
    if pc is not None:
        if pc > 1.2:
            s -= 0.10; risks.append(f"[options] P/C={pc:.2f} 看跌活跃")
        elif pc < 0.7:
            s += 0.05; pts.append(f"[options] P/C={pc:.2f} 看涨活跃")
    # 微结构（成交量放大 vs. 均值）
    vol_ratio = f.get("vol_ratio_20d")
    if vol_ratio is not None:
        if vol_ratio > 1.5:
            pts.append(f"[微结构] 成交量 {vol_ratio:.2f}x 20 日均量放大")
            s += 0.05
        elif vol_ratio < 0.6:
            pts.append(f"[微结构] 成交量 {vol_ratio:.2f}x 萎缩")
            s -= 0.03
    # 情感分（已在 sentiment analyst 里，但这里再交叉印证）
    if state.sentiment_signal:
        sg = state.sentiment_signal.score
        if sg > 0.3: s += 0.08; pts.append(f"[综合] 舆情正面 {sg:+.2f}")
        elif sg < -0.3: s -= 0.08; risks.append(f"[综合] 舆情负面 {sg:+.2f}")
    if not risks:
        risks.append("[综合] 综合信号中性，参考单因子分析师意见")
    if not pts:
        pts.append("[综合] options / 微结构因子缺失，转由技术+基本面主导")
    catalysts.append("options 到期日")
    catalysts.append("大宗交易/盘后异动")
    return AnalystVerdict(
        analyst="portfolio_view",
        direction=_score_to_direction(s), score=round(s, 3),
        confidence=round(min(0.9, 0.35 + abs(s)), 2),
        key_points=pts[:5], risks=risks[:4], catalysts=catalysts[:3], horizon_days=15)


# ---------- LLM 上下文渲染 ----------
def _render_ctx(state, analyst: str) -> str:
    parts = [f"标的={state.ticker} 日期={state.as_of}"]
    if state.market_data and state.market_data.bars:
        b = state.market_data.bars[-1]
        parts.append(f"最新收盘={b.close} 开={b.open} 高={b.high} 低={b.low} 量={b.volume}")
    if analyst in ("technical", "fundamental") and state.factor_bundle:
        rows = ", ".join(f"{f.name}={round(f.value,4)}" for f in state.factor_bundle.factors)
        parts.append("因子: " + rows)
    if analyst == "sentiment" and state.sentiment_signal:
        sig = state.sentiment_signal
        parts.append(f"舆情分={sig.score} 覆盖={sig.volume} 主要话题={sig.top_topics}")
        for n in sig.news_used[:8]:
            parts.append(f"- [{n.ts.date()}] {n.title[:80]}")
    if analyst == "macro_event" and state.alt_signals:
        parts.append(f"宏观={state.alt_signals.macro_regime} 龙虎榜={state.alt_signals.lhb_net_buy} 大宗={state.alt_signals.block_trade_amount}")
    if analyst == "portfolio_view":
        if state.factor_bundle:
            options = [f for f in state.factor_bundle.factors if f.category in ("options", "microstructure")]
            if options:
                parts.append("options+微结构因子: " + ", ".join(f"{f.name}={round(f.value,4)}" for f in options))
        if state.sentiment_signal:
            parts.append(f"综合舆情分={state.sentiment_signal.score} 覆盖={state.sentiment_signal.volume}")
    return "\n".join(parts)


_SYS = {
    "technical": "你是资深技术分析师。基于价量因子给出方向。key_points ≤5 条，用因子数值支撑。risks ≥1。",
    "fundamental": "你是资深基本面分析师。基于给到的因子与价格代理，谨慎给出中长期方向。risks ≥1，务必声明数据局限。",
    "sentiment": "你是舆情分析师。区分 price-in 和新边际；只讨论新闻中真实提到的事实。risks ≥1。",
    "macro_event": "你是宏观/事件分析师。指明当前 regime 与临近的重要事件。risks ≥1。",
}


async def _run(state, analyst: str, heuristic_fn) -> AnalystVerdict:
    """LLM 优先；若返回 None (无 key/失败/校验错) 则用启发式。"""
    if client.enabled:
        v = await client.structured("deep", _SYS[analyst], _render_ctx(state, analyst), AnalystVerdict)
        if v is not None:
            v.analyst = analyst
            if not v.risks:
                v.risks = ["模型未输出风险，已由系统补充默认项"]
            return v
    return heuristic_fn(state)


async def technical(state):   return await _run(state, "technical",   _heuristic_technical)
async def fundamental(state): return await _run(state, "fundamental", _heuristic_fundamental)
async def sentiment(state):   return await _run(state, "sentiment",   _heuristic_sentiment)
async def macro_event(state): return await _run(state, "macro_event", _heuristic_macro_event)

async def portfolio_view(state): return await _run(state, "portfolio_view", _heuristic_portfolio_view)
