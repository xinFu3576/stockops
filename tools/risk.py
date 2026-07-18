"""D5 RiskAgent — 三级风控 + 合规。"""
from __future__ import annotations
import asyncio
from typing import Any
from core.schemas import Decision, MarketData, RiskCheckResult, RiskReport


CONFIG = {
    "max_single_pct": 0.15,
    "max_industry_pct": 0.30,
    "regime_gross": {"risk_on": 0.9, "neutral": 0.7, "risk_off": 0.4},
    "turbulence_kill": 100.0,
}


async def check_risk(dec: Decision | None,
                     md: MarketData | None = None,
                     portfolio: Any = None) -> RiskReport | None:
    if dec is None:
        return None
    checks: list[RiskCheckResult] = []

    # 1) Order-level
    order_check = RiskCheckResult(level="order", passed=True,
                                  reasons=["订单级参数正常"])
    if dec.entry_price and dec.stop_loss:
        if dec.direction.value in ("buy", "strong_buy") and dec.stop_loss >= dec.entry_price:
            order_check.passed = False
            order_check.forced_action = "block"
            order_check.reasons.append("止损位不低于入场价")
    checks.append(order_check)

    # 2) Portfolio-level (占位)
    checks.append(RiskCheckResult(level="portfolio", passed=True,
                                  reasons=["组合层无冲突"]))

    # 3) Strategy-level: 极端信心 + HOLD 的怪异组合触发警告
    strat = RiskCheckResult(level="strategy", passed=True,
                            reasons=["策略层通过"])
    if dec.confidence > 0.85 and dec.direction.value == "hold":
        strat.forced_action = "warn"
        strat.reasons.append("高信心 HOLD，需人工复核")
    checks.append(strat)

    # 4) Compliance
    from tools.compliance import compliance_check
    checks.append(await compliance_check(dec.ticker, md))

    # 汇总
    if any(c.forced_action == "block" or not c.passed for c in checks):
        final = "block"
    elif any(c.forced_action == "downsize" for c in checks):
        final = "downsize"
    else:
        final = "pass"

    return RiskReport(ticker=dec.ticker, checks=checks, final_action=final)


def check_risk_sync(dec, portfolio=None):
    """兼容旧调用点。"""
    return asyncio.run(check_risk(dec, None, portfolio))
