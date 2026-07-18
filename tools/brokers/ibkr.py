"""IBKR paper broker stub via ib-insync 协议(未连线时返回 stub result)。

真接线要求:
  1. 安装 ib-insync: pip install ib_insync
  2. 本地起 IB Gateway/TWS,paper account port 4002/7497,允许 API
  3. 环境变量: IBKR_HOST=127.0.0.1  IBKR_PORT=4002  IBKR_CLIENT_ID=42

未满足 → 优雅降级为 stub(status=stub,不改账户),不 crash。
"""
from __future__ import annotations
import asyncio, os, uuid
from datetime import datetime, timezone

from .base import OrderResult
from core.schemas import Order as OrderIntent


def _cfg():
    return {
        "host": os.environ.get("IBKR_HOST", "127.0.0.1"),
        "port": int(os.environ.get("IBKR_PORT", "4002")),
        "cid": int(os.environ.get("IBKR_CLIENT_ID", "42")),
    }


class IBKRPaperBroker:
    name = "ibkr_paper"

    def __init__(self):
        self._ib = None

    async def _connect(self):
        if self._ib is not None:
            return self._ib
        try:
            import ib_insync as ibs
        except ImportError:
            return None
        cfg = _cfg()
        try:
            ib = ibs.IB()
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, lambda: ib.connect(cfg["host"], cfg["port"], clientId=cfg["cid"], timeout=5)),
                timeout=8,
            )
            self._ib = ib
            return ib
        except Exception:
            return None

    async def place_order(self, o: OrderIntent) -> OrderResult:
        ib = await self._connect()
        if ib is None:
            return OrderResult(
                order_id=str(uuid.uuid4())[:8],
                ticker=o.ticker, side=o.side, qty=o.qty, price=o.price or 0.0,
                filled_qty=0, filled_price=0.0, status="stub",
                ts=datetime.now(timezone.utc), broker=self.name,
                reason="ib_insync 未安装或 gateway 未开;降级 stub,未真实下单"
            )
        try:
            import ib_insync as ibs
            symbol = o.ticker.split(".")[0]
            contract = ibs.Stock(symbol, "SMART", "USD")
            action = "BUY" if o.side.lower() == "buy" else "SELL"
            order = (ibs.LimitOrder(action, o.qty, o.price) if o.order_type == "limit"
                     else ibs.MarketOrder(action, o.qty))
            trade = ib.placeOrder(contract, order)
            await asyncio.get_event_loop().run_in_executor(None, lambda: ib.sleep(2))
            filled = trade.orderStatus.filled or 0
            avg = trade.orderStatus.avgFillPrice or o.price or 0.0
            status = trade.orderStatus.status.lower() if trade.orderStatus.status else "accepted"
            return OrderResult(
                order_id=str(trade.order.orderId), ticker=o.ticker, side=o.side,
                qty=o.qty, price=o.price or 0.0, filled_qty=int(filled),
                filled_price=float(avg), status=status,
                ts=datetime.now(timezone.utc), broker=self.name,
                reason=f"remaining={trade.orderStatus.remaining}"
            )
        except Exception as e:
            return OrderResult(
                order_id=str(uuid.uuid4())[:8],
                ticker=o.ticker, side=o.side, qty=o.qty, price=o.price or 0.0,
                filled_qty=0, filled_price=0.0, status="rejected",
                ts=datetime.now(timezone.utc), broker=self.name, reason=f"ibkr 异常: {e}"
            )

    async def positions(self) -> dict[str, dict]:
        ib = await self._connect()
        if ib is None: return {}
        out = {}
        for p in ib.positions():
            out[p.contract.symbol] = {"qty": int(p.position), "cost": float(p.avgCost)}
        return out

    async def cash(self) -> float:
        ib = await self._connect()
        if ib is None: return 0.0
        for v in ib.accountValues():
            if v.tag == "TotalCashValue" and v.currency == "USD":
                return float(v.value)
        return 0.0
    async def health(self) -> dict:
        """诊断:gateway 是否可连、账户是否可读。"""
        try:
            import ib_insync  # noqa
        except ImportError:
            return {"ok": False, "reason": "ib_insync 未安装 (pip install ib_insync)"}
        ib = await self._connect()
        if ib is None:
            cfg = _cfg()
            return {"ok": False, "reason": f"无法连接 IB Gateway {cfg['host']}:{cfg['port']} (client_id={cfg['cid']})"}
        try:
            cash = await self.cash()
            return {"ok": True, "cash": cash, "positions": len(await self.positions())}
        except Exception as e:
            return {"ok": False, "reason": f"{type(e).__name__}: {e}"}
