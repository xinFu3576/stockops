"""v0.14.0: adapt-portfolio_view + advise --json/--execute + HK IV skew + dashboard /api/notify."""
import asyncio
import pytest
from datetime import date
from unittest.mock import patch


def test_adapt_includes_portfolio_view():
    from tools import adapt
    assert "portfolio_view" in adapt.ANALYSTS
    assert "portfolio_view" in adapt.DEFAULT_WEIGHTS
    assert adapt.TAG_RE.search("[portfolio_view] test")


def test_to_json_summary_structure():
    from tools.advise_pipeline import to_json_summary
    from core.orchestrator import AgentState
    from core.schemas import Decision, Direction

    dec = Decision(ticker="AAPL", as_of=date(2026,1,1),
                   direction=Direction.BUY, score=70, confidence=0.6,
                   horizon_days=20, entry_price=200, stop_loss=190, take_profit=220,
                   key_points=["kp1"], used_analysts=["technical"], risks=["r1"], catalysts=["c1"])
    st = AgentState(ticker="AAPL", as_of=date(2026,1,1), mode="dry_run", decision=dec)
    out = {"orders": [], "states": [st], "portfolio_adjust": None,
           "t1_violations": {}, "overview": None, "backtest": []}
    s = to_json_summary(out)
    assert s["decisions"][0]["ticker"] == "AAPL"
    assert s["decisions"][0]["direction"] == "buy"
    assert s["decisions"][0]["score"] == 70
    assert s["orders"] == []


def test_execute_advise_orders_skips_zero_qty(tmp_path, monkeypatch):
    import tools.brokers.paper as pb_mod
    monkeypatch.setattr(pb_mod, "STATE", tmp_path / "acc.json")
    monkeypatch.setattr(pb_mod, "LEDGER", tmp_path / "ledger.json")
    from core.schemas import Order
    from tools.advise_pipeline import execute_advise_orders
    orders = [Order(ticker="AAPL", side="buy", qty=100, price=200, order_type="limit")]
    # 强制 adjusted qty = 0
    r = asyncio.run(execute_advise_orders(orders, portfolio_adjust={"adjusted": {"AAPL": 0}}))
    assert r["count"] == 1
    assert r["orders"][0]["status"] == "skipped"


def test_execute_advise_orders_places_buy(tmp_path, monkeypatch):
    import tools.brokers.paper as pb_mod
    monkeypatch.setattr(pb_mod, "STATE", tmp_path / "acc.json")
    monkeypatch.setattr(pb_mod, "LEDGER", tmp_path / "ledger.json")
    from core.schemas import Order
    from tools.advise_pipeline import execute_advise_orders
    orders = [Order(ticker="AAPL", side="buy", qty=100, price=200, order_type="limit")]
    r = asyncio.run(execute_advise_orders(orders))
    assert r["count"] == 1
    assert r["orders"][0]["status"] == "filled"


def test_execute_advise_blocks_t1_same_day_sell(tmp_path, monkeypatch):
    import tools.brokers.paper as pb_mod
    monkeypatch.setattr(pb_mod, "STATE", tmp_path / "acc.json")
    monkeypatch.setattr(pb_mod, "LEDGER", tmp_path / "ledger.json")
    from core.schemas import Order
    from tools.advise_pipeline import execute_advise_orders
    # 先买
    asyncio.run(execute_advise_orders([Order(ticker="600519.SS", side="buy", qty=100, price=1600, order_type="limit")]))
    # 当日 sell 应被拦
    r = asyncio.run(execute_advise_orders([Order(ticker="600519.SS", side="sell", qty=100, price=1650, order_type="limit")]))
    assert r["orders"][0]["status"] == "blocked"
    assert "T+1" in r["orders"][0]["reason"]


def test_fetch_futu_hk_no_futu_lib():
    """无 futu 库时应返回 None，不 crash。"""
    from tools import options_chain as oc
    # Force ImportError
    import sys
    with patch.dict(sys.modules, {"futu": None}):
        assert oc.fetch_futu_hk("0700.HK") is None
    # 非 HK 直接 None
    assert oc.fetch_futu_hk("AAPL") is None


def test_fetch_aastocks_hk_non_hk_none():
    from tools.options_chain import fetch_aastocks_hk
    assert fetch_aastocks_hk("AAPL") is None


def test_options_health_reports_hk_sources():
    from tools.options_chain import health
    h = health()
    assert "futu_hk" in h
    assert "aastocks_hk" in h


def test_dashboard_notify_endpoint_exists():
    src = open("dashboard/server.py").read()
    assert "/api/notify" in src
    assert "_notify_sync" in src
    assert "推送到微信/飞书" in src


def test_advise_options_hk_uses_futu_chain_first():
    """HK ticker 走 futu → aastocks → tradier → polygon 降级链。"""
    src = open("tools/options_chain.py").read()
    assert "fetch_futu_hk, fetch_aastocks_hk, fetch_tradier, fetch_polygon" in src
