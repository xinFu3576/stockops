"""ReportingAgent — 决策仪表盘。"""
from __future__ import annotations

DIRECTION_CN = {
    "strong_buy": "🟢 强烈买入", "buy": "🟢 买入",
    "hold": "🟡 观望", "sell": "🔴 卖出", "strong_sell": "🔴 强烈卖出",
}


async def render(state) -> str:
    d = state.decision
    if d is None:
        return f"# {state.ticker} @ {state.as_of}\n(no decision)"
    lines = []
    lines.append(f"# 🎯 {state.as_of} 决策仪表盘 · {state.ticker}")
    lines.append("")
    lines.append(f"**方向**: {DIRECTION_CN.get(d.direction, d.direction)}  ·  **评分**: {d.score}  ·  **置信度**: {d.confidence:.2f}")
    lines.append(f"**时间视角**: {d.horizon_days} 天")
    if d.entry_price:
        ep = round(d.entry_price, 3)
        sl = round(d.stop_loss, 3) if d.stop_loss else "—"
        tp = round(d.take_profit, 3) if d.take_profit else "—"
        lines.append(f"**参考位**: 现价 {ep} · 止损 {sl} · 止盈 {tp}")
    lines.append("")
    lines.append("## 📊 关键论据")
    for k in d.key_points:
        lines.append(f"- {k}")
    lines.append("")
    lines.append("## 🚨 风险警报")
    for r in d.risks:
        lines.append(f"- {r}")
    if d.catalysts:
        lines.append("")
        lines.append("## ✨ 催化因素")
        for c in d.catalysts:
            lines.append(f"- {c}")
    if d.checklist:
        lines.append("")
        lines.append("## ✅ 操作检查清单")
        for c in d.checklist:
            lines.append(f"- {c}")
    if state.risk:
        lines.append("")
        lines.append(f"## 🛡 风控裁决: {state.risk.final_action}")
    return "\n".join(lines)
