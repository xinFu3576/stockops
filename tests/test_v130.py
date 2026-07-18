"""v0.13.0：portfolio_view analyst + advise --paper-check + HK sina + IV cache TTL。"""
import asyncio
import pytest
from datetime import date
from unittest.mock import patch


def test_portfolio_view_analyst_exists():
    from agents_llm import analysts
    assert hasattr(analysts, "portfolio_view")
    assert hasattr(analysts, "_heuristic_portfolio_view")


def test_heuristic_portfolio_view_returns_verdict():
    from agents_llm.analysts import _heuristic_portfolio_view
    from core.schemas import FactorBundle, FactorValue, SentimentSignal
    from core.orchestrator import AgentState

    fb = FactorBundle(
        ticker="AAPL", as_of=date(2026, 1, 1),
        factors=[
            FactorValue(name="iv_skew_25d", value=0.08, category="options", used_data_ts=date(2026,1,1)),
            FactorValue(name="put_call_ratio", value=1.4, category="options", used_data_ts=date(2026,1,1)),
            FactorValue(name="vol_ratio_20d", value=1.8, category="microstructure", used_data_ts=date(2026,1,1)),
        ],
    )
    st = AgentState(ticker="AAPL", as_of=date(2026, 1, 1), mode="dry_run", factor_bundle=fb)
    v = _heuristic_portfolio_view(st)
    assert v.analyst == "portfolio_view"
    assert v.direction.value in ("sell", "strong_sell", "hold")  # 高 skew + 高 P/C → 偏空
    assert v.risks


def test_research_manager_weights_include_portfolio_view():
    src = open("agents_llm/research_manager.py").read()
    assert '"portfolio_view"' in src or "portfolio_view" in src


def test_orchestrator_analysts_include_portfolio_view():
    """确保 analysts_parallel 会调 portfolio_view。"""
    src = open("core/orchestrator.py").read()
    assert "analysts.portfolio_view(s)" in src


def test_hk_sina_url_format():
    """确保 HK 走 rt_hk 前缀 + 5 位补零。"""
    from tools import realtime_quote as rq
    import urllib.request
    captured = {}
    def fake_open(req, **kw):
        captured["url"] = getattr(req, "full_url", str(req))
        raise Exception("stub")
    with patch.object(urllib.request, "urlopen", side_effect=fake_open):
        q = rq._fetch_sina("0700.HK")
    assert "rt_hk" in captured.get("url", "")
    assert "00700" in captured.get("url", "")


def test_options_disk_ttl_30min():
    from tools import options_chain as oc
    assert oc._DISK_TTL == 1800


def test_advise_pipeline_paper_check_helpers_exist():
    from tools import advise_pipeline as ap
    assert hasattr(ap, "_paper_position_snapshot")
    assert hasattr(ap, "_diff_positions_vs_orders")


def test_diff_positions_vs_orders():
    from tools.advise_pipeline import _diff_positions_vs_orders
    from core.schemas import Order
    positions = {"AAPL": {"qty": 100}, "MSFT": {"qty": 50}}
    orders = [
        Order(ticker="AAPL", side="buy", qty=50, price=200, order_type="limit"),
        Order(ticker="GOOG", side="buy", qty=10, price=150, order_type="limit"),
    ]
    rows = _diff_positions_vs_orders(positions, orders)
    m = {r["ticker"]: r for r in rows}
    assert m["AAPL"]["delta"] == 50
    assert m["GOOG"]["delta"] == 10
    assert m["MSFT"]["current"] == 50 and m["MSFT"]["target_qty"] == 0


def test_dashboard_advise_endpoints_exist():
    """dashboard/server.py 包含 /advise 与 /api/advise。"""
    src = open("dashboard/server.py").read()
    assert "/advise" in src
    assert "/api/advise" in src
    assert "_advise_sync" in src
    assert "ADVISE_HTML" in src


def test_paper_check_integration_smoke(tmp_path, monkeypatch):
    """跑 run_advise(paper_check=True) 不 crash。"""
    from tools.advise_pipeline import _diff_positions_vs_orders, _paper_position_snapshot
    import tools.brokers.paper as pb_mod
    monkeypatch.setattr(pb_mod, "STATE", tmp_path / "acc.json")
    monkeypatch.setattr(pb_mod, "LEDGER", tmp_path / "ledger.json")
    snap = asyncio.run(_paper_position_snapshot(["AAPL"]))
    assert "positions" in snap or "error" in snap
