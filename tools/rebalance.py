"""持仓再平衡引擎：目标权重 → 现持仓 → 生成买/卖 orders。

支持三种权重来源：
1. Kelly 公式（基于 Decision.confidence 与 score）
2. Equal-weight 分散
3. Risk-parity（用 factor_bundle 里的 rv_expansion 反比配权）

再平衡触发：
- schedule: 每日/每周
- drift: 单标的偏离目标 > tolerance (默认 5%)
- decision_change: 决策方向翻转
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from core.schemas import Order, Decision, Direction


@dataclass
class Position:
    ticker: str
    qty: int
    avg_cost: float = 0.0
    market_price: float = 0.0
    sector: str = ""

    @property
    def market_value(self) -> float:
        return self.qty * (self.market_price or self.avg_cost)


@dataclass
class RebalancePlan:
    target_weights: dict[str, float]
    current_weights: dict[str, float]
    orders: list[Order] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    tolerance: float = 0.05
    total_equity: float = 0.0


def _kelly_weight(dec: Decision, kelly_frac: float = 0.5) -> float:
    """半 Kelly：w = f * (score - 0.5) * confidence * direction_sign。"""
    if dec is None: return 0.0
    sign = 1 if dec.direction in (Direction.BUY, Direction.STRONG_BUY) else \
           -1 if dec.direction in (Direction.SELL, Direction.STRONG_SELL) else 0
    if sign == 0: return 0.0
    # 用 direction sign 决定符号，magnitude 用 |edge|
    edge_mag = abs(dec.score - 50) / 50.0   # 0..1
    return max(-0.4, min(0.4, kelly_frac * edge_mag * dec.confidence * sign))


def compute_target_weights(
    decisions: dict[str, Decision],
    method: str = "kelly",
    factor_bundles: dict | None = None,
    max_single: float = 0.20,
    cash_floor: float = 0.10,
) -> dict[str, float]:
    """目标权重：sum(|w|) + cash = 1，做多 w>0，做空 w<0。"""
    if not decisions: return {}
    raw: dict[str, float] = {}
    if method == "kelly":
        for tk, d in decisions.items():
            raw[tk] = _kelly_weight(d)
    elif method == "equal":
        actives = [tk for tk, d in decisions.items()
                   if d.direction in (Direction.BUY, Direction.STRONG_BUY, Direction.SELL, Direction.STRONG_SELL)]
        if not actives: return {}
        w = (1 - cash_floor) / len(actives)
        for tk, d in decisions.items():
            if tk not in actives: continue
            sign = 1 if d.direction in (Direction.BUY, Direction.STRONG_BUY) else -1
            raw[tk] = w * sign
    elif method == "risk_parity":
        # inverse-vol weighting
        vols = {}
        for tk in decisions:
            fb = (factor_bundles or {}).get(tk, {})
            rv = fb.get("rv_expansion") or 1.0
            vols[tk] = max(rv, 0.2)
        inv = {tk: 1 / v for tk, v in vols.items()}
        s = sum(inv.values())
        for tk, d in decisions.items():
            sign = 1 if d.direction in (Direction.BUY, Direction.STRONG_BUY) else \
                   -1 if d.direction in (Direction.SELL, Direction.STRONG_SELL) else 0
            raw[tk] = inv[tk] / s * (1 - cash_floor) * sign
    else:
        raise ValueError(f"unknown method: {method}")

    # cap single weight
    capped = {tk: max(-max_single, min(max_single, w)) for tk, w in raw.items()}
    return capped


def build_rebalance_plan(
    target_weights: dict[str, float],
    positions: dict[str, Position],
    prices: dict[str, float],
    total_equity: float,
    tolerance: float = 0.05,
    lot_size: dict[str, int] | None = None,
) -> RebalancePlan:
    """生成 diff orders。CN A 股整百手，港股不同 lot，US 单股。"""
    lot_size = lot_size or {}

    def _lot(tk: str) -> int:
        if tk in lot_size: return lot_size[tk]
        tk_u = tk.upper()
        if tk_u.endswith((".SS", ".SH", ".SZ")): return 100
        if tk_u.endswith(".HK"): return 100
        return 1

    plan = RebalancePlan(
        target_weights=target_weights,
        current_weights={},
        tolerance=tolerance,
        total_equity=total_equity,
    )

    # 计算当前权重
    for tk, pos in positions.items():
        p = prices.get(tk) or pos.market_price or pos.avg_cost or 0
        plan.current_weights[tk] = (pos.qty * p) / total_equity if total_equity > 0 else 0

    all_tks = set(target_weights) | set(positions)
    for tk in sorted(all_tks):
        tgt = target_weights.get(tk, 0.0)
        cur = plan.current_weights.get(tk, 0.0)
        drift = tgt - cur
        if abs(drift) < tolerance:
            plan.reasons.append(f"[{tk}] 无需再平衡 (drift={drift:+.1%} < ±{tolerance:.0%})")
            continue
        price = prices.get(tk)
        if not price:
            plan.reasons.append(f"[{tk}] 缺 price，跳过")
            continue
        # 目标手数
        tgt_qty = int((tgt * total_equity) / price)
        cur_qty = positions.get(tk, Position(ticker=tk, qty=0)).qty
        diff_qty = tgt_qty - cur_qty
        lot = _lot(tk)
        diff_qty = (diff_qty // lot) * lot
        if diff_qty == 0:
            plan.reasons.append(f"[{tk}] diff 不足一手 (lot={lot})")
            continue
        # 目标为负 = 空头 → sell open；现持仓正 → sell close
        side = "buy" if diff_qty > 0 else "sell"
        # 目标为负仓位（空单）且现无仓：转为 sell（开空）
        if tgt < 0 and cur_qty == 0:
            side = "sell"
        plan.orders.append(Order(
            ticker=tk, side=side, qty=abs(diff_qty), price=price, order_type="limit",
            tag=f"rebal:{cur:+.1%}→{tgt:+.1%}",
        ))
        plan.reasons.append(f"[{tk}] {side} {abs(diff_qty)} @ {price} (cur {cur:+.1%} → tgt {tgt:+.1%})")

    return plan


def apply_kelly_sizing(orders: list[Order], decisions: dict[str, Decision],
                       total_equity: float) -> list[Order]:
    """对已有 orders 用 Kelly 二次缩放：低 confidence → 小仓位。"""
    out = []
    for o in orders:
        d = decisions.get(o.ticker)
        if d is None:
            out.append(o); continue
        k = abs(_kelly_weight(d))
        if k < 0.02:
            continue
        if o.price:
            max_qty = int((k * total_equity) / o.price)
            new_qty = min(o.qty, max_qty)
            if o.ticker.upper().endswith((".SS", ".SH", ".SZ", ".HK")):
                new_qty = (new_qty // 100) * 100
            if new_qty <= 0: continue
            out.append(Order(
                ticker=o.ticker, side=o.side, qty=new_qty, price=o.price,
                order_type=o.order_type,
                tag=(o.tag or "") + f"|kelly_{k:.2f}",
            ))
        else:
            out.append(o)
    return out
