"""Trader — Decision → Orders，使用 Fractional Kelly 动态仓位。

仓位公式：
  f* = clip((edge / variance) * fraction, 0, max_weight)
其中：
  edge     = (score - 50) / 50 * confidence      # [-1,1] 边缘
  variance = ATR/price 的平方（近 14 日）        # 单日波动率²
  fraction = 0.25 (1/4 Kelly，风控)
  max      = 0.10 单标的
非 A 股不做整手；A 股 100 股一手。
"""
from __future__ import annotations
from core.schemas import Order, Direction


KELLY_FRACTION = 0.25
MAX_SINGLE_WEIGHT = 0.10
MIN_TRADE_NOTIONAL = 5000.0  # 低于此金额不下单
ACCOUNT_SIZE = 100_000.0     # TODO: 由 portfolio 提供


def _atr_over_price(state) -> float | None:
    if not state.factor_bundle or not state.market_data or not state.market_data.bars:
        return None
    atr = next((f.value for f in state.factor_bundle.factors if f.name == "atr_14"), None)
    p = state.market_data.bars[-1].close
    if atr is None or p <= 0:
        return None
    return float(atr) / float(p)


def _kelly_weight(score: int, confidence: float, sigma: float | None) -> float:
    """核心：目标仓位百分比。"""
    if sigma is None or sigma <= 0:
        return 0.05  # 保守兜底
    edge = (score - 50) / 50.0 * confidence
    if abs(edge) < 0.05:
        return 0.0
    kelly = edge / (sigma ** 2)
    w = kelly * KELLY_FRACTION
    return max(-MAX_SINGLE_WEIGHT, min(MAX_SINGLE_WEIGHT, w))


async def build_orders(state) -> list[Order]:
    dec = state.decision
    if dec is None or dec.direction == Direction.HOLD:
        return []

    sigma = _atr_over_price(state)
    weight = _kelly_weight(dec.score, dec.confidence, sigma)
    if weight == 0:
        return []

    side = "buy" if dec.direction in (Direction.BUY, Direction.STRONG_BUY) else "sell"
    price = dec.entry_price
    if price is None and state.market_data and state.market_data.bars:
        price = state.market_data.bars[-1].close
    if not price or price <= 0:
        return []

    notional = ACCOUNT_SIZE * abs(weight)
    if notional < MIN_TRADE_NOTIONAL:
        return []

    qty = int(notional / price)
    if dec.ticker.upper().endswith((".SS", ".SH", ".SZ")):
        qty = (qty // 100) * 100
    if qty <= 0:
        return []

    tag = f"kelly_{weight:+.3f}_sigma_{sigma:.3f}" if sigma else "kelly_fallback"
    return [Order(ticker=dec.ticker, side=side, qty=qty,
                  price=round(price, 2), order_type="limit", tag=tag)]
