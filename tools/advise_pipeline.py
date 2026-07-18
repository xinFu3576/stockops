"""cmd_advise v0.12.0：整合实时价、组合层、LLM 综合看法、T+1 违规提示、advise 回测。"""
from __future__ import annotations
import asyncio, pathlib
from datetime import date, datetime
from typing import Any


ACTION_MAP = {
    "strong_buy": "🚀 **强烈买入**",
    "buy":        "✅ **买入**",
    "hold":       "⏸ **持有/观望**",
    "sell":       "🚫 **卖出**",
    "strong_sell": "🔻 **强烈卖出**",
}


def _fmt_num(x):
    if x is None: return "-"
    if isinstance(x, float): return f"{x:.2f}"
    return str(x)


def _lot_size(ticker: str) -> int:
    tk = ticker.upper()
    if tk.endswith((".SS", ".SH", ".SZ", ".HK")):
        return 100
    return 1


async def _t1_violations(tickers: list[str], today) -> dict[str, bool]:
    """检查 paper broker 里 open_date==today 且是 A 股的持仓。"""
    try:
        from tools.brokers.paper import PaperBroker
        pb = PaperBroker()
        lots = await pb.position_open_dates()
    except Exception:
        return {}
    from tools.rebalance import is_t_plus_1
    today_s = today.isoformat() if hasattr(today, "isoformat") else str(today)
    violations = {}
    for tk in tickers:
        if not is_t_plus_1(tk):
            continue
        tk_lots = lots.get(tk, [])
        # 是否有 today 买入的 lot
        if any(l.get("date") == today_s and l.get("qty", 0) > 0 for l in tk_lots):
            violations[tk] = True
    return violations


async def _llm_overview(sections: list[dict]) -> str | None:
    """LLM 3-5 句综合看法。"""
    try:
        from agents_llm.llm_client import client
        if not client.enabled:
            return None
        # 组织简洁上下文
        bullets = []
        for s in sections:
            bullets.append(
                f"- {s['ticker']} [{s['market']}]：{s['action']} 分{s['score']} 信心{s['conf']:.0%}"
                f"，止损{s.get('sl')}，止盈{s.get('tp')}，风险 {s.get('risk_head')}"
            )
        prompt = (
            "你是一位资深港美 + A 股组合经理。基于下列每标的的建议，给出 3-5 句人话"
            "综合看法：覆盖仓位倾向、行业/相关性提示、宏观/情绪风险和当日执行注意事项。\n"
            + "\n".join(bullets)
        )
        txt = await client.chat(
            tier="deep",
            system="用中文回答，控制在 5 句内，专业但直白。",
            user=prompt,
            temperature=0.4,
            max_tokens=350,
        )
        return txt
    except Exception:
        return None



async def _run_states(tickers, as_of):
    from core.orchestrator import run_one
    tasks = [run_one(tk, as_of, mode="dry_run", force=True) for tk in tickers]
    return await asyncio.gather(*tasks)


def _entry_from_realtime(tk, fallback_close):
    """优先取实时报价；失败回落收盘价。"""
    try:
        from tools.realtime_quote import get_quote
        q = get_quote(tk)
        if q and q.price and q.price > 0:
            return q.price, q.source, q.change_pct
    except Exception:
        pass
    return fallback_close, "close", None


def _build_orders(states, equity):
    """把 direction+entry+qty 转成 Order 列表，供组合层再平衡。"""
    from core.schemas import Order
    from tools.rebalance import _kelly_weight
    orders = []
    per_ticker = {}
    for st in states:
        dec = st.decision
        if dec is None:
            continue
        tk = st.ticker
        entry_close = None
        if st.market_data and st.market_data.bars:
            entry_close = st.market_data.bars[-1].close
        entry_price, entry_source, chg = _entry_from_realtime(tk, entry_close or 0)
        if dec.entry_price and dec.entry_price > 0 and entry_source == "close":
            entry_price = dec.entry_price
        pos_frac = abs(_kelly_weight(dec))
        pos_notional = equity * pos_frac
        if entry_price and entry_price > 0:
            qty = int(pos_notional / entry_price)
            lot = _lot_size(tk)
            qty = (qty // lot) * lot
        else:
            qty = 0
        side = None
        if dec.direction.value in ("buy", "strong_buy"):
            side = "buy"
        elif dec.direction.value in ("sell", "strong_sell"):
            side = "sell"
        if side and qty > 0 and entry_price:
            orders.append(Order(
                ticker=tk, side=side, qty=qty, price=entry_price,
                order_type="limit", tag="advise_v0.12"
            ))
        per_ticker[tk] = {
            "entry_price": entry_price,
            "entry_source": entry_source,
            "change_pct": chg,
            "qty": qty,
            "side": side,
            "pos_frac": pos_frac,
        }
    return orders, per_ticker


def _apply_portfolio(states, orders, equity):
    """组合层：行业敞口 + 相关性 集群 → 调整后 qty。"""
    if not orders:
        return {}
    try:
        from tools.portfolio import rebalance
    except Exception:
        return {}
    mds = {}
    sectors = {}
    for st in states:
        if st.market_data:
            mds[st.ticker] = st.market_data
        sec = None
        if st.fundamentals:
            sec = st.fundamentals.get("sector")
        sectors[st.ticker] = sec
    try:
        adj = rebalance(orders, mds, sectors, account=equity)
    except Exception:
        return {}
    return {
        "adjusted": {o.ticker: o.qty for o in adj.orders},
        "violations": adj.violations,
        "industry_weights": adj.industry_weights,
    }


def backtest_advise(states):
    """对每个 ticker 跑 run_backtest(dec, md)，聚合胜率/Sharpe/MaxDD。"""
    from tools.backtest import run_backtest
    rows = []
    for st in states:
        if st.decision is None or st.market_data is None:
            continue
        try:
            m = run_backtest(st.decision, st.market_data)
            if m is None: continue
            rows.append({
                "ticker": st.ticker,
                "annual_return": m.annual_return,
                "sharpe": m.sharpe,
                "max_drawdown": m.max_drawdown,
                "win_rate": m.win_rate,
                "total_return": m.total_return,
            })
        except Exception as e:
            rows.append({"ticker": st.ticker, "error": str(e)[:80]})
    return rows


async def run_advise(tickers, as_of, equity, include_backtest=False, use_llm=True, paper_check=False):
    """异步核心：跑 states → orders → portfolio → LLM 综合 → markdown。"""
    from tools.rebalance import is_t_plus_1, estimate_cost
    from tools.options_chain import fetch_options_skew
    from tools.investment_news import load_latest, aggregate_sentiment
    from core.schemas import Order

    states = await _run_states(tickers, as_of)
    orders, per_tk = _build_orders(states, equity)
    port = _apply_portfolio(states, orders, equity)
    adjusted = (port.get("adjusted") or {}) if port else {}
    port_violations = (port.get("violations") or []) if port else []
    industry_w = (port.get("industry_weights") or {}) if port else {}

    # T+1 违规检查
    t1_viol = await _t1_violations(tickers, as_of)

    # sentiment
    try:
        snap = load_latest()
        sent_all = aggregate_sentiment(snap.get("items", []), tickers=tickers) if snap else {}
    except Exception:
        sent_all = {}

    lines = [f"# 🎯 StockOps 交易建议 · {as_of.isoformat()}", ""]
    if industry_w:
        lines.append("**组合层行业敞口**：" + ", ".join(f"{k} {v:.1%}" for k, v in industry_w.items()))
    if port_violations:
        for v in port_violations:
            lines.append(f"> ⚠️ {v}")
    if industry_w or port_violations:
        lines.append("")

    llm_sections = []
    payload_sections = {}
    for st in states:
        tk = st.ticker
        dec = st.decision
        if dec is None:
            lines.append(f"## {tk}")
            lines.append("❌ 决策生成失败（数据/分析师异常）")
            lines.append("")
            continue
        t_plus = "T+1" if is_t_plus_1(tk) else "T+0"
        act = ACTION_MAP.get(dec.direction.value, "?")
        meta = per_tk.get(tk, {})
        entry = meta.get("entry_price") or dec.entry_price or 0
        entry_src = meta.get("entry_source", "close")
        chg = meta.get("change_pct")
        orig_qty = meta.get("qty") or 0
        adj_qty = adjusted.get(tk, orig_qty) if orig_qty else 0
        pos_frac = meta.get("pos_frac") or 0

        # options
        opt_line = ""
        try:
            opt = fetch_options_skew(tk)
            if opt and opt.iv_skew is not None:
                opt_line = f"IV skew={opt.iv_skew:+.4f} ({opt.source})"
            elif opt and opt.put_call_ratio:
                opt_line = f"P/C={opt.put_call_ratio:.2f}"
        except Exception:
            pass

        # sentiment 单标的
        tk_agg = sent_all.get(tk.upper()) or sent_all.get("_MARKET")
        sent_line = ""
        if tk_agg:
            sent_line = f"全网情绪 {tk_agg.get('label')} ({tk_agg.get('avg'):+.3f}, n={tk_agg.get('count')})"

        # 成本
        cost_info = ""
        if entry and adj_qty and meta.get("side"):
            try:
                o = Order(ticker=tk, side=meta["side"], qty=adj_qty, price=entry, order_type="limit")
                c = estimate_cost(o)
                cost_info = f"预估成本 ¥{c['total']:.2f} ({c['total_bps']:.1f} bps)"
            except Exception:
                pass

        lines.append(f"## {tk} · {t_plus}")
        entry_note = ""
        if entry_src == "yahoo" or entry_src == "sina":
            entry_note = f" ({entry_src} 实时"
            if chg is not None:
                entry_note += f", {chg:+.2f}%"
            entry_note += ")"
        lines.append(f"{act} · 评分 **{dec.score}/100** · 信心 **{dec.confidence:.0%}**")
        if entry:
            lines.append(f"- 建议入场价 **{_fmt_num(entry)}**{entry_note} · 止损 **{_fmt_num(dec.stop_loss)}** · 止盈 **{_fmt_num(dec.take_profit)}** · 持有 ~{dec.horizon_days} 天")
        if orig_qty:
            if adj_qty != orig_qty:
                lines.append(f"- 建议数量 **{adj_qty}** 股（原 {orig_qty}，组合层调整）· 占用 {pos_frac:.1%} of ¥{equity:,.0f}")
            else:
                lines.append(f"- 建议数量 **{adj_qty}** 股（半 Kelly, 占用 {pos_frac:.1%} of ¥{equity:,.0f}）")
        if cost_info: lines.append(f"- {cost_info}")
        if is_t_plus_1(tk):
            lines.append(f"- ⚠️ **A 股 T+1**：当日买入的股票不能当日卖出")
        if t1_viol.get(tk) and meta.get("side") == "sell":
            lines.append(f"- 🛑 **T+1 违规提示**：paper 账户在 {as_of.isoformat()} 已买入 {tk}，当日 sell 会被拒单")
        if sent_line: lines.append(f"- {sent_line}")
        if opt_line: lines.append(f"- {opt_line}")
        if dec.key_points:
            lines.append(f"- **关键点**：")
            for k in dec.key_points[:5]:
                lines.append(f"  - {k}")
        if dec.risks:
            lines.append(f"- **风险**：")
            for r in dec.risks[:5]:
                lines.append(f"  - {r}")
        if dec.catalysts:
            lines.append(f"- **催化**：")
            for c in dec.catalysts[:4]:
                lines.append(f"  - {c}")
        lines.append("")

        llm_sections.append({
            "ticker": tk, "market": t_plus, "action": act,
            "score": dec.score, "conf": dec.confidence,
            "sl": dec.stop_loss, "tp": dec.take_profit,
            "risk_head": (dec.risks[0][:40] if dec.risks else "无"),
        })
        payload_sections.setdefault("决策", []).append(
            f"{tk} [{t_plus}] {act} 分{dec.score} 信心{dec.confidence:.0%} qty={adj_qty}"
        )
        if dec.risks:
            payload_sections.setdefault("风险", []).extend([f"{tk}: {r[:60]}" for r in dec.risks[:2]])

    # LLM 综合看法
    overview = None
    if use_llm and llm_sections:
        overview = await _llm_overview(llm_sections)
    if overview:
        lines.append("## 🧠 综合看法（LLM）")
        lines.append(overview)
        lines.append("")
    elif use_llm:
        lines.append("_（未配置 LLM_API_KEY，跳过综合看法）_\n")

    # advise 回测
    bt_rows = []
    if include_backtest:
        bt_rows = backtest_advise(states)
        if bt_rows:
            lines.append("## 📊 回测评估（历史）")
            lines.append("| Ticker | 年化 | Sharpe | MaxDD | 胜率 |")
            lines.append("|---|---|---|---|---|")
            for r in bt_rows:
                if "error" in r:
                    lines.append(f"| {r['ticker']} | err | err | err | err |")
                else:
                    lines.append(
                        f"| {r['ticker']} | {r['annual_return']:+.2%} | "
                        f"{r['sharpe']:+.2f} | {r['max_drawdown']:.2%} | {r['win_rate']:.0%} |"
                    )
            lines.append("")

    return {
        "markdown": "\n".join(lines),
        "payload_sections": payload_sections,
        "states": states,
        "orders": orders,
        "portfolio_adjust": port,
        "t1_violations": t1_viol,
        "overview": overview,
        "backtest": bt_rows,
    }


async def _paper_position_snapshot(tickers: list[str]):
    """从 paper broker 拿当前持仓 & 现金。"""
    try:
        from tools.brokers.paper import PaperBroker
        pb = PaperBroker()
        pos = await pb.positions()
        cash = await pb.cash()
    except Exception as e:
        return {"error": str(e)}
    subset = {tk: pos[tk] for tk in tickers if tk in pos}
    return {"positions": subset, "cash": cash, "other_positions": {k: v for k, v in pos.items() if k not in tickers}}


def _diff_positions_vs_orders(positions: dict, orders: list) -> list[dict]:
    """把每个 ticker 的 current qty 和 suggested qty (from orders) 对齐。"""
    from collections import defaultdict
    sug = defaultdict(lambda: {"qty": 0, "side": "-"})
    for o in orders:
        sug[o.ticker]["qty"] = o.qty
        sug[o.ticker]["side"] = o.side
    all_tk = set(positions.keys()) | set(sug.keys())
    rows = []
    for tk in sorted(all_tk):
        cur = positions.get(tk, {}).get("qty", 0)
        s = sug.get(tk) or {"qty": 0, "side": "-"}
        diff = 0
        if s["side"] == "buy":
            diff = s["qty"]         # add
        elif s["side"] == "sell":
            diff = -min(cur, s["qty"])
        rows.append({
            "ticker": tk, "current": cur, "action": s.get("side", "-"),
            "target_qty": s.get("qty", 0), "delta": diff,
        })
    return rows


def to_json_summary(out: dict) -> dict:
    """把 run_advise 输出转 JSON 可序列化摘要 (供 --json / API 消费)。"""
    from datetime import date, datetime
    orders = []
    for o in out.get("orders") or []:
        orders.append({
            "ticker": o.ticker, "side": o.side, "qty": o.qty,
            "price": o.price, "order_type": o.order_type, "tag": o.tag,
        })
    decisions = []
    for st in out.get("states") or []:
        dec = st.decision
        if dec is None:
            decisions.append({"ticker": st.ticker, "error": "decision missing"})
            continue
        decisions.append({
            "ticker": st.ticker,
            "as_of": dec.as_of.isoformat() if hasattr(dec.as_of, "isoformat") else str(dec.as_of),
            "direction": dec.direction.value,
            "score": dec.score,
            "confidence": dec.confidence,
            "entry_price": dec.entry_price,
            "stop_loss": dec.stop_loss,
            "take_profit": dec.take_profit,
            "horizon_days": dec.horizon_days,
            "key_points": dec.key_points,
            "risks": dec.risks,
            "catalysts": dec.catalysts,
            "used_analysts": dec.used_analysts,
        })
    return {
        "orders": orders,
        "decisions": decisions,
        "portfolio_adjust": {
            "adjusted": (out.get("portfolio_adjust") or {}).get("adjusted", {}),
            "violations": (out.get("portfolio_adjust") or {}).get("violations", []),
            "industry_weights": (out.get("portfolio_adjust") or {}).get("industry_weights", {}),
        } if out.get("portfolio_adjust") else None,
        "t1_violations": out.get("t1_violations") or {},
        "overview": out.get("overview"),
        "backtest": out.get("backtest") or [],
        "paper_diff": out.get("paper_diff"),
    }


async def execute_advise_orders(orders: list, portfolio_adjust: dict | None = None,
                                skip_t1_violations: bool = True) -> dict:
    """把 advise 建议下到 paper broker。返回每单结果。"""
    from tools.brokers.paper import PaperBroker
    from tools.rebalance import is_t_plus_1
    pb = PaperBroker()
    results = []
    # 优先使用 portfolio 调整后的 qty
    adj_qty = (portfolio_adjust or {}).get("adjusted") or {}
    for o in orders:
        qty = adj_qty.get(o.ticker, o.qty)
        if qty <= 0:
            results.append({"ticker": o.ticker, "status": "skipped", "reason": "adjusted qty=0"})
            continue
        # T+1 违规检查：同日 buy 后 sell 会被拦
        if skip_t1_violations and o.side == "sell" and is_t_plus_1(o.ticker):
            lots = await pb.position_open_dates()
            from datetime import date as _d
            today = _d.today().isoformat()
            if any(l.get("date") == today for l in lots.get(o.ticker, [])):
                results.append({"ticker": o.ticker, "status": "blocked",
                                "reason": "T+1: 当日买入不能卖出"})
                continue
        from core.schemas import Order
        real = Order(ticker=o.ticker, side=o.side, qty=qty,
                     price=o.price, order_type=o.order_type or "limit", tag=o.tag or "advise")
        try:
            r = await pb.place_order(real)
            results.append({"ticker": o.ticker, "side": o.side, "qty": qty,
                            "price": o.price, "status": r.status,
                            "reason": getattr(r, "reason", None)})
        except Exception as e:
            results.append({"ticker": o.ticker, "status": "error", "reason": str(e)[:120]})
    return {"orders": results, "count": len(results)}
