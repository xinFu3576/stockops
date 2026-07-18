from datetime import date
import pytest
from core.schemas import Decision, Direction, Order


def test_decision_requires_risks():
    with pytest.raises(Exception):
        Decision(ticker="AAPL", as_of=date(2026,7,17), direction=Direction.HOLD,
                 score=50, confidence=0.5, key_points=["a"], risks=[], used_analysts=[])


def test_decision_valid_minimal():
    d = Decision(ticker="AAPL", as_of=date(2026,7,17), direction=Direction.HOLD,
                 score=50, confidence=0.5, key_points=["a"], risks=["r"],
                 used_analysts=["technical"])
    assert d.score == 50


def test_order_types():
    o = Order(ticker="AAPL", side="buy", qty=100, price=200.0)
    assert o.side == "buy"


def test_microstructure_bundle():
    from datetime import date
    from core.schemas import MarketData, Bar, Market
    bars = []
    import random
    random.seed(42)
    price = 100.0
    for i in range(60):
        o = price
        c = price + random.uniform(-2, 2)
        h = max(o, c) + random.uniform(0, 1)
        l = min(o, c) - random.uniform(0, 1)
        bars.append(Bar(date=date(2026, 1, 1), open=o, high=h, low=l, close=c,
                        volume=1_000_000 + random.randint(-100000, 200000)))
        price = c
    md = MarketData(ticker="TEST", market=Market.US, as_of=date(2026, 1, 1),
                    bars=bars, source="test", health="ok")
    from tools.microstructure import compute_microstructure_bundle
    out = compute_microstructure_bundle(md)
    assert "ofi_5d" in out and "iv_skew_proxy" in out
    for k, v in out.items():
        assert v is None or -2 <= v <= 2, f"{k}={v} out of sane range"
