"""v0.12.0 测试：realtime cache / 组合叠加 / advise-backtest / T+1 open_date。"""
import pytest, asyncio
from datetime import date
from unittest.mock import patch, MagicMock


def test_realtime_quote_cache():
    """cache 结构存在 + get_quote 三级降级不 crash。"""
    from tools import realtime_quote as rq
    # mock 两级都失败
    with patch.object(rq, "_fetch_yahoo", return_value=None), \
         patch.object(rq, "_fetch_sina", return_value=None):
        q = rq.get_quote("XXXXX_UNKNOWN")
        assert q is None

    # mock yahoo 成功
    fake = rq.Quote(ticker="AAPL", price=200.0, source="yahoo", ts=0)
    with patch.object(rq, "_fetch_yahoo", return_value=fake):
        q = rq.get_quote("AAPL")
        assert q and q.price == 200.0 and q.source == "yahoo"


def test_advise_pipeline_import():
    from tools import advise_pipeline as ap
    assert hasattr(ap, "run_advise")
    assert hasattr(ap, "backtest_advise")
    assert hasattr(ap, "_build_orders")
    assert hasattr(ap, "_apply_portfolio")


def test_build_orders_uses_realtime_price():
    from tools import advise_pipeline as ap
    from core.schemas import Decision, Direction, MarketData, Bar, Market
    from core.orchestrator import AgentState
    md = MarketData(ticker="AAPL", market=Market.US, as_of=date(2026, 1, 1), source="test",
                    bars=[Bar(date=date(2026, 1, 1), open=100, high=101, low=99, close=100, volume=1000)])
    dec = Decision(ticker="AAPL", as_of=date(2026, 1, 1),
                   direction=Direction.BUY, score=70, confidence=0.65, horizon_days=20,
                   entry_price=100, stop_loss=95, take_profit=110,
                   key_points=[], used_analysts=[], risks=["test risk"], catalysts=[])
    st = AgentState(ticker="AAPL", as_of=date(2026, 1, 1), mode="dry_run",
                    market_data=md, decision=dec)
    # mock realtime
    with patch("tools.advise_pipeline._entry_from_realtime",
               return_value=(210.0, "yahoo", 1.2)):
        orders, meta = ap._build_orders([st], equity=100000)
    assert meta["AAPL"]["entry_price"] == 210.0
    assert meta["AAPL"]["entry_source"] == "yahoo"
    assert len(orders) == 1
    assert orders[0].side == "buy"


def test_paper_broker_records_open_date(tmp_path, monkeypatch):
    """paper broker buy 后 open_date/lots 写入。"""
    import tools.brokers.paper as pb_mod
    monkeypatch.setattr(pb_mod, "STATE", tmp_path / "acc.json")
    monkeypatch.setattr(pb_mod, "LEDGER", tmp_path / "ledger.json")
    from core.schemas import Order
    pb = pb_mod.PaperBroker()
    order = Order(ticker="600519.SS", side="buy", qty=100, price=1600, order_type="limit")
    res = asyncio.run(pb.place_order(order))
    assert res.status == "filled"
    lots = asyncio.run(pb.position_open_dates())
    assert "600519.SS" in lots
    assert len(lots["600519.SS"]) == 1
    assert lots["600519.SS"][0]["qty"] == 100
    assert "date" in lots["600519.SS"][0]


def test_paper_broker_fifo_sell(tmp_path, monkeypatch):
    """sell 消费 lots (FIFO)。"""
    import tools.brokers.paper as pb_mod
    monkeypatch.setattr(pb_mod, "STATE", tmp_path / "acc.json")
    monkeypatch.setattr(pb_mod, "LEDGER", tmp_path / "ledger.json")
    from core.schemas import Order
    pb = pb_mod.PaperBroker()
    asyncio.run(pb.place_order(Order(ticker="AAPL", side="buy", qty=100, price=200, order_type="limit")))
    asyncio.run(pb.place_order(Order(ticker="AAPL", side="buy", qty=50, price=210, order_type="limit")))
    lots = asyncio.run(pb.position_open_dates())
    assert sum(l["qty"] for l in lots["AAPL"]) == 150
    asyncio.run(pb.place_order(Order(ticker="AAPL", side="sell", qty=120, price=215, order_type="limit")))
    lots2 = asyncio.run(pb.position_open_dates())
    remain = sum(l["qty"] for l in lots2["AAPL"])
    assert remain == 30


def test_t1_violation_detection(tmp_path, monkeypatch):
    """A 股 same-day buy → sell 会被 detect。"""
    from tools.advise_pipeline import _t1_violations
    import tools.brokers.paper as pb_mod
    monkeypatch.setattr(pb_mod, "STATE", tmp_path / "acc.json")
    monkeypatch.setattr(pb_mod, "LEDGER", tmp_path / "ledger.json")
    from core.schemas import Order
    pb = pb_mod.PaperBroker()
    asyncio.run(pb.place_order(Order(ticker="600519.SS", side="buy", qty=100, price=1600, order_type="limit")))
    today = date.today()
    v = asyncio.run(_t1_violations(["600519.SS", "AAPL"], today))
    assert v.get("600519.SS") is True
    assert v.get("AAPL") is None or v.get("AAPL") is False


def test_apply_portfolio_no_orders():
    from tools.advise_pipeline import _apply_portfolio
    assert _apply_portfolio([], [], 100000) == {}


def test_llm_client_chat_disabled(monkeypatch):
    """未配置 API key 时 chat 返回 None，不 crash。"""
    from agents_llm.llm_client import LLMClient
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    c = LLMClient()
    r = asyncio.run(c.chat("deep", "sys", "user"))
    assert r is None


def test_backtest_advise_empty():
    from tools.advise_pipeline import backtest_advise
    assert backtest_advise([]) == []
