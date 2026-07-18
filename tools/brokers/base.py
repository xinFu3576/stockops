from __future__ import annotations
from datetime import datetime
from typing import Protocol
from pydantic import BaseModel

from core.schemas import Order as OrderIntent


class OrderResult(BaseModel):
    order_id: str
    ticker: str
    side: str
    qty: int
    price: float
    filled_qty: int
    filled_price: float
    status: str          # accepted | filled | rejected
    ts: datetime
    broker: str
    reason: str = ""


class Broker(Protocol):
    name: str
    async def place_order(self, o: OrderIntent) -> OrderResult: ...
    async def positions(self) -> dict[str, dict]: ...
    async def cash(self) -> float: ...
