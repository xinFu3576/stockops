"""PaperBroker:本地虚拟账户,按订单价格立即撮合,持久化到 data/paper/。
提供 positions/cash 供 portfolio 消费,让"paper"闭环。"""
from __future__ import annotations
import json, os, uuid
from datetime import datetime, timezone
from pathlib import Path

from .base import OrderResult
from core.schemas import Order as OrderIntent


ROOT = Path(__file__).resolve().parents[2]
PAPER_DIR = ROOT / "data" / "paper"
PAPER_DIR.mkdir(parents=True, exist_ok=True)
LEDGER = PAPER_DIR / "ledger.json"
STATE = PAPER_DIR / "account.json"


DEFAULT_CASH = float(os.environ.get("STOCKOPS_PAPER_CASH", "1000000"))  # 1M 默认


def _load_state():
    if STATE.exists():
        return json.load(open(STATE))
    return {"cash": DEFAULT_CASH, "positions": {}}


def _save_state(st):
    json.dump(st, open(STATE, "w"), ensure_ascii=False, indent=2)


def _append_ledger(entry):
    arr = []
    if LEDGER.exists():
        try: arr = json.load(open(LEDGER))
        except Exception: pass
    arr.append(entry)
    json.dump(arr, open(LEDGER, "w"), ensure_ascii=False, indent=2)


class PaperBroker:
    name = "paper"

    async def place_order(self, o: OrderIntent) -> OrderResult:
        st = _load_state()
        gross = o.qty * o.price
        fee = gross * 0.0003  # 0.03% 综合费,粗糙
        oid = str(uuid.uuid4())[:8]

        if o.side.lower() == "buy":
            need = gross + fee
            if st["cash"] < need:
                res = OrderResult(order_id=oid, ticker=o.ticker, side=o.side, qty=o.qty, price=o.price,
                                  filled_qty=0, filled_price=0.0, status="rejected",
                                  ts=datetime.now(timezone.utc), broker=self.name,
                                  reason=f"cash 不足 (需 {need:.2f},余 {st['cash']:.2f})")
                _append_ledger({"result": res.model_dump(mode="json"), "state": st})
                return res
            st["cash"] -= need
            pos = st["positions"].setdefault(o.ticker, {"qty": 0, "cost": 0.0})
            new_qty = pos["qty"] + o.qty
            pos["cost"] = (pos["qty"] * pos["cost"] + gross) / new_qty if new_qty else 0
            pos["qty"] = new_qty
        else:  # sell
            pos = st["positions"].get(o.ticker, {"qty": 0, "cost": 0.0})
            if pos["qty"] < o.qty:
                res = OrderResult(order_id=oid, ticker=o.ticker, side=o.side, qty=o.qty, price=o.price,
                                  filled_qty=0, filled_price=0.0, status="rejected",
                                  ts=datetime.now(timezone.utc), broker=self.name,
                                  reason=f"持仓不足 (需 {o.qty},持 {pos['qty']})")
                _append_ledger({"result": res.model_dump(mode="json"), "state": st})
                return res
            st["cash"] += gross - fee
            pos["qty"] -= o.qty
            if pos["qty"] == 0:
                st["positions"].pop(o.ticker, None)

        _save_state(st)
        res = OrderResult(order_id=oid, ticker=o.ticker, side=o.side, qty=o.qty, price=o.price,
                          filled_qty=o.qty, filled_price=o.price, status="filled",
                          ts=datetime.now(timezone.utc), broker=self.name,
                          reason=f"手续费 {fee:.2f}")
        _append_ledger({"result": res.model_dump(mode="json"), "state": st})
        return res

    async def positions(self) -> dict[str, dict]:
        return _load_state()["positions"]

    async def cash(self) -> float:
        return _load_state()["cash"]
