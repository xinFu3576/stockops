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
        if isinstance(v, str): continue
        assert v is None or -2 <= v <= 2, f"{k}={v} out of sane range"


def test_investment_news_normalize_and_dedup():
    from tools.investment_news import _norm, _hash, _extract_a_tickers, keyword_filter, ticker_filter
    items = [
        {"title":"A", "url":"http://x.com/1", "ts":"2026-07-18T10:00:00+00:00", "tags":[]},
        {"title":"A", "url":"http://x.com/1?utm=abc", "ts":"2026-07-18T09:00:00+00:00", "tags":[]},
        {"title":"B", "url":"http://y.com/2", "ts":"2026-07-18T11:00:00+00:00", "tags":["policy"]},
    ]
    out = _norm(items)
    assert len(out) == 2
    # 排序: newer first
    assert out[0]["title"] == "B"

    # Ticker 抽取
    assert "600519.SS" in _extract_a_tickers("茅台 600519 涨停")
    assert "000858.SZ" in _extract_a_tickers("五粮液 000858 传闻")

    # 关键词过滤
    assert len(keyword_filter([{"title":"降息", "summary":""},{"title":"加班","summary":""}], ["降息"])) == 1
    # ticker 过滤
    assert len(ticker_filter([{"tickers":["AAPL"]},{"tickers":["MSFT"]}], ["AAPL"])) == 1


def test_notify_wecom_returns_false_when_unset(monkeypatch):
    """微信渠道未配置时应静默返回 False,不 crash。"""
    monkeypatch.delenv("WECOM_WEBHOOK", raising=False)
    monkeypatch.delenv("SERVERCHAN_KEY", raising=False)
    from tools.notify import send_wecom, send_serverchan, notify
    assert send_wecom("t","b") is False
    assert send_serverchan("t","b") is False
    r = notify("t","b")
    assert r == {"feishu": False, "wecom": False, "serverchan": False, "smtp": False}
