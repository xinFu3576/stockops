"""富途 OpenAPI paper broker stub(需 futu-opend 网关)。

真接线要求:
  1. pip install futu-api
  2. 本地起 futu-opend(11111 端口),paper account
  3. 环境变量: FUTU_HOST=127.0.0.1 FUTU_PORT=11111 FUTU_ACCT=xxx

未满足 → 优雅降级 stub。
"""
from __future__ import annotations
import os, uuid
from datetime import datetime, timezone

from .base import OrderResult
from core.schemas import Order as OrderIntent


class FutuPaperBroker:
    name = "futu_paper"

    async def place_order(self, o: OrderIntent) -> OrderResult:
        try:
            from futu import OpenSecTradeContext, TrdMarket, TrdEnv, OrderType, TrdSide
        except ImportError:
            return OrderResult(
                order_id=str(uuid.uuid4())[:8],
                ticker=o.ticker, side=o.side, qty=o.qty, price=o.price or 0.0,
                filled_qty=0, filled_price=0.0, status="stub",
                ts=datetime.now(timezone.utc), broker=self.name,
                reason="futu-api 未安装;降级 stub"
            )
        # 更多接线细节由用户根据市场(A/HK/US)填 TrdMarket
        return OrderResult(
            order_id=str(uuid.uuid4())[:8],
            ticker=o.ticker, side=o.side, qty=o.qty, price=o.price or 0.0,
            filled_qty=0, filled_price=0.0, status="stub",
            ts=datetime.now(timezone.utc), broker=self.name,
            reason="futu 骨架已就绪,请填市场/账号细节后启用"
        )

    async def positions(self) -> dict[str, dict]:
        return {}

    async def cash(self) -> float:
        return 0.0
