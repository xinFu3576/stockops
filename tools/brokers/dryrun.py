from __future__ import annotations
import uuid
from datetime import datetime, timezone

from .base import OrderResult
from core.schemas import Order as OrderIntent


class DryRunBroker:
    name = "dry_run"

    async def place_order(self, o: OrderIntent) -> OrderResult:
        return OrderResult(
            order_id=str(uuid.uuid4())[:8],
            ticker=o.ticker, side=o.side, qty=o.qty, price=o.price,
            filled_qty=0, filled_price=0.0,
            status="accepted", ts=datetime.now(timezone.utc),
            broker=self.name, reason="dry_run 不真实执行"
        )

    async def positions(self) -> dict[str, dict]:
        return {}

    async def cash(self) -> float:
        return 0.0

    async def health(self) -> dict:
        return {"ok": True, "note": "dry_run 无外部依赖"}
