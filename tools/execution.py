"""D6 ExecutionAgent — 通过 brokers 适配层执行(dry_run/paper/live)。"""
from __future__ import annotations
from datetime import datetime
from core.schemas import Order, Fill
from tools.brokers import get_broker


async def execute(orders: list[Order], mode: str) -> list[Fill]:
    broker = get_broker(mode)
    fills: list[Fill] = []
    for i, o in enumerate(orders):
        r = await broker.place_order(o)
        fills.append(Fill(
            order_ref=r.order_id,
            filled_qty=r.filled_qty,
            avg_price=r.filled_price or (o.price or 0.0),
            ts=r.ts,
            mode="paper" if mode == "paper" else ("live" if mode == "live" else "dry_run"),
        ))
    return fills


async def execute_v2(orders, mode):
    """带 OrderResult 明细的版本;给 stock_execution agent 用。"""
    broker = get_broker(mode)
    return [await broker.place_order(o) for o in orders]
