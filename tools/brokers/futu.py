"""富途 OpenAPI paper broker(SIMULATE 模式)。需 futu-opend 网关运行。

真接线要求:
  1. pip install futu-api  # 或 pip install stockops[futu]
  2. 本地起 futu-opend (默认 11111 端口),登录账号
  3. 环境变量:
       FUTU_HOST=127.0.0.1
       FUTU_PORT=11111
       FUTU_MARKET=HK|US|CN         (默认 HK)
       FUTU_TRD_ENV=SIMULATE|REAL   (默认 SIMULATE = 富途模拟盘)
       FUTU_ACC_ID=<acc_id>         (可选,不填用首个)
       FUTU_PWD_UNLOCK=<交易解锁密码> (真盘必填,模拟盘可空)

未满足 → 优雅降级 status=stub,不 crash。
"""
from __future__ import annotations
import os, uuid
from datetime import datetime, timezone

from .base import OrderResult
from core.schemas import Order as OrderIntent


def _cfg():
    return {
        "host": os.environ.get("FUTU_HOST", "127.0.0.1"),
        "port": int(os.environ.get("FUTU_PORT", "11111")),
        "market": os.environ.get("FUTU_MARKET", "HK").upper(),
        "env": os.environ.get("FUTU_TRD_ENV", "SIMULATE").upper(),
        "acc_id": os.environ.get("FUTU_ACC_ID"),
        "pwd": os.environ.get("FUTU_PWD_UNLOCK", ""),
    }


def _futu_code(ticker: str, market: str) -> str:
    """AAPL -> US.AAPL; 0700.HK -> HK.00700; 600519.SS -> SH.600519; 000858.SZ -> SZ.000858"""
    t = ticker.upper()
    if t.endswith(".SS"): return f"SH.{t.replace('.SS','')}"
    if t.endswith(".SZ"): return f"SZ.{t.replace('.SZ','')}"
    if t.endswith(".HK"):
        code = t.replace(".HK","").lstrip("0").zfill(5)
        return f"HK.{code}"
    return f"{market}.{t}"


class FutuPaperBroker:
    name = "futu_paper"

    def __init__(self):
        self._trd = None

    def _stub(self, o: OrderIntent, reason: str) -> OrderResult:
        return OrderResult(
            order_id=str(uuid.uuid4())[:8],
            ticker=o.ticker, side=o.side, qty=o.qty, price=o.price or 0.0,
            filled_qty=0, filled_price=0.0, status="stub",
            ts=datetime.now(timezone.utc), broker=self.name, reason=reason,
        )

    def _connect(self):
        if self._trd is not None: return self._trd
        try:
            from futu import OpenSecTradeContext, TrdMarket, SecurityFirm
        except ImportError:
            return None
        cfg = _cfg()
        try:
            market_map = {"HK": TrdMarket.HK, "US": TrdMarket.US, "CN": TrdMarket.CN}
            self._trd = OpenSecTradeContext(
                filter_trdmarket=market_map.get(cfg["market"], TrdMarket.HK),
                host=cfg["host"], port=cfg["port"], security_firm=SecurityFirm.FUTUSECURITIES,
            )
            return self._trd
        except Exception:
            return None

    def _acc_id(self, trd):
        cfg = _cfg()
        if cfg["acc_id"]: return int(cfg["acc_id"])
        try:
            from futu import TrdEnv
            env = TrdEnv.SIMULATE if cfg["env"] == "SIMULATE" else TrdEnv.REAL
            ret, data = trd.get_acc_list()
            if ret == 0 and len(data):
                same_env = data[data["trd_env"] == env]
                return int((same_env if len(same_env) else data).iloc[0]["acc_id"])
        except Exception: pass
        return None

    async def place_order(self, o: OrderIntent) -> OrderResult:
        trd = self._connect()
        if trd is None:
            return self._stub(o, "futu-api 未装或 opend 未启动;降级 stub")
        try:
            from futu import OrderType, TrdSide, TrdEnv, RET_OK
            cfg = _cfg()
            env = TrdEnv.SIMULATE if cfg["env"] == "SIMULATE" else TrdEnv.REAL
            side = TrdSide.BUY if o.side.lower() == "buy" else TrdSide.SELL
            ot = OrderType.NORMAL if (o.order_type or "limit") == "limit" else OrderType.MARKET
            code = _futu_code(o.ticker, cfg["market"])
            acc_id = self._acc_id(trd)
            if env == TrdEnv.REAL and cfg["pwd"]:
                trd.unlock_trade(cfg["pwd"])
            ret, data = trd.place_order(
                price=float(o.price or 0.0), qty=int(o.qty), code=code,
                trd_side=side, order_type=ot, trd_env=env,
                acc_id=acc_id if acc_id else 0,
            )
            if ret != RET_OK:
                return OrderResult(
                    order_id=str(uuid.uuid4())[:8], ticker=o.ticker, side=o.side,
                    qty=o.qty, price=o.price or 0.0, filled_qty=0, filled_price=0.0,
                    status="rejected", ts=datetime.now(timezone.utc),
                    broker=self.name, reason=f"futu 拒单: {data}",
                )
            row = data.iloc[0]
            filled = int(row.get("dealt_qty", 0) or 0)
            avg = float(row.get("dealt_avg_price", 0) or (o.price or 0))
            return OrderResult(
                order_id=str(row.get("order_id", "")), ticker=o.ticker,
                side=o.side, qty=o.qty, price=o.price or 0.0,
                filled_qty=filled, filled_price=avg,
                status=str(row.get("order_status", "accepted")).lower(),
                ts=datetime.now(timezone.utc), broker=self.name,
                reason=f"env={cfg['env']} code={code}",
            )
        except Exception as e:
            return self._stub(o, f"futu 异常: {type(e).__name__}: {e}")

    async def positions(self) -> dict[str, dict]:
        trd = self._connect()
        if trd is None: return {}
        try:
            from futu import TrdEnv, RET_OK
            cfg = _cfg()
            env = TrdEnv.SIMULATE if cfg["env"] == "SIMULATE" else TrdEnv.REAL
            acc_id = self._acc_id(trd)
            ret, data = trd.position_list_query(trd_env=env, acc_id=acc_id if acc_id else 0)
            if ret != RET_OK: return {}
            out = {}
            for _, r in data.iterrows():
                out[r["code"]] = {"qty": int(r["qty"]), "cost": float(r.get("cost_price", 0))}
            return out
        except Exception:
            return {}

    async def cash(self) -> float:
        trd = self._connect()
        if trd is None: return 0.0
        try:
            from futu import TrdEnv, Currency, RET_OK
            cfg = _cfg()
            env = TrdEnv.SIMULATE if cfg["env"] == "SIMULATE" else TrdEnv.REAL
            acc_id = self._acc_id(trd)
            ret, data = trd.accinfo_query(trd_env=env, acc_id=acc_id if acc_id else 0)
            if ret != RET_OK: return 0.0
            return float(data.iloc[0].get("cash", 0))
        except Exception:
            return 0.0

    async def health(self) -> dict:
        """诊断:opend 是否可连、账户是否可读。"""
        trd = self._connect()
        if trd is None:
            return {"ok": False, "reason": "futu-api 未装或 opend 未启动"}
        try:
            acc = self._acc_id(trd)
            return {"ok": True, "acc_id": acc, "env": _cfg()["env"], "market": _cfg()["market"]}
        except Exception as e:
            return {"ok": False, "reason": f"{type(e).__name__}: {e}"}
