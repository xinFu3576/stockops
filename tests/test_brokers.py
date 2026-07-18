import asyncio
from core.schemas import Order
from tools.brokers import get_broker


def _run(coro): return asyncio.run(coro)


def test_dryrun_never_fills():
    o = Order(ticker="AAPL", side="buy", qty=1, price=1.0)
    r = _run(get_broker("dry_run").place_order(o))
    assert r.status == "accepted" and r.filled_qty == 0


def test_paper_fills_and_persists(tmp_path, monkeypatch):
    # 隔离 paper 目录
    import tools.brokers.paper as pp
    monkeypatch.setattr(pp, "PAPER_DIR", tmp_path)
    monkeypatch.setattr(pp, "LEDGER", tmp_path / "ledger.json")
    monkeypatch.setattr(pp, "STATE", tmp_path / "account.json")
    monkeypatch.setattr(pp, "DEFAULT_CASH", 100_000)

    b = get_broker("paper")
    r = _run(b.place_order(Order(ticker="AAPL", side="buy", qty=10, price=100.0)))
    assert r.status == "filled" and r.filled_qty == 10
    r2 = _run(b.place_order(Order(ticker="AAPL", side="buy", qty=10_000, price=100.0)))
    assert r2.status == "rejected"


def test_ibkr_gracefully_stub():
    r = _run(get_broker("ibkr").place_order(Order(ticker="AAPL", side="buy", qty=1, price=1.0)))
    assert r.status in ("stub", "rejected")  # 无 ib_insync / gateway


def test_futu_gracefully_stub():
    r = _run(get_broker("futu").place_order(Order(ticker="0700.HK", side="buy", qty=100, price=300.0)))
    assert r.status in ("stub", "rejected")


def test_all_brokers_have_health():
    for name in ("dry_run", "paper", "ibkr", "futu"):
        b = get_broker(name)
        assert hasattr(b, "health"), f"{name} broker 缺少 health()"
        h = _run(b.health())
        assert "ok" in h, f"{name}.health() 应含 ok 字段: {h}"
