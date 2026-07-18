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
