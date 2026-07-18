"""v0.9.0 契约测试: options chain / rebalance / A/B."""
import os
from datetime import date
from core.schemas import Decision, Direction, Order
from tools.rebalance import (Position, compute_target_weights, build_rebalance_plan,
                              apply_kelly_sizing, _kelly_weight)


_D = lambda t,d,s,c: Decision(ticker=t, as_of=date.today(), direction=d, score=s,
                                confidence=c, key_points=[], risks=['x'], catalysts=[], used_analysts=[])


def test_kelly_weight_buy():
    d = _D('X', Direction.BUY, 70, 0.7)
    w = _kelly_weight(d)
    assert w > 0 and w <= 0.4

def test_kelly_weight_hold_zero():
    d = _D('X', Direction.HOLD, 50, 0.5)
    assert _kelly_weight(d) == 0.0

def test_kelly_weight_sell_negative():
    d = _D('X', Direction.STRONG_SELL, 20, 0.6)
    assert _kelly_weight(d) < 0

def test_compute_target_weights_kelly():
    dec = {'A': _D('A', Direction.BUY, 75, 0.7), 'B': _D('B', Direction.HOLD, 50, 0.5)}
    w = compute_target_weights(dec, method='kelly')
    assert 'A' in w and w['A'] > 0
    assert w['B'] == 0.0

def test_compute_target_weights_equal():
    dec = {'A': _D('A', Direction.BUY, 60, 0.6), 'B': _D('B', Direction.SELL, 40, 0.6)}
    w = compute_target_weights(dec, method='equal')
    assert w['A'] > 0 and w['B'] < 0

def test_build_rebalance_plan_generates_orders():
    dec = {'A': _D('A', Direction.STRONG_BUY, 85, 0.75)}
    w = compute_target_weights(dec, method='kelly')
    positions = {}
    plan = build_rebalance_plan(w, positions, {'A': 100}, total_equity=100_000, tolerance=0.03)
    assert len(plan.orders) == 1
    assert plan.orders[0].side == 'buy'

def test_build_rebalance_plan_trims_over_position():
    dec = {'A': _D('A', Direction.BUY, 60, 0.5)}
    w = compute_target_weights(dec, method='kelly')
    # 现持仓 50%，目标 <20%，应生成 sell
    positions = {'A': Position(ticker='A', qty=500, avg_cost=100, market_price=100)}
    plan = build_rebalance_plan(w, positions, {'A': 100}, total_equity=100_000)
    sells = [o for o in plan.orders if o.side == 'sell']
    assert len(sells) >= 1

def test_options_chain_no_key_returns_none():
    from tools.options_chain import fetch_options_skew, health
    os.environ.pop('TRADIER_API_KEY', None)
    os.environ.pop('POLYGON_API_KEY', None)
    h = health()
    assert h['tradier'] == 'no_key'
    assert fetch_options_skew('AAPL') is None

def test_microstructure_falls_back_to_proxy():
    from tools.microstructure import compute_microstructure_bundle
    from core.schemas import MarketData, Bar, Market
    from datetime import datetime, timezone
    bars = [Bar(date=datetime(2026,1,i+1).date(), open=100+i*0.5, high=101+i*0.5,
                low=99+i*0.5, close=100+i*0.5, volume=10000+i*10) for i in range(30)]
    md = MarketData(ticker='TESTX', market=Market.US, as_of=date.today(), source='test', bars=bars)
    b = compute_microstructure_bundle(md)
    assert 'iv_skew' in b
    assert b.get('iv_skew_source') in ('tradier', 'polygon', 'proxy')
