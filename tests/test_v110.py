"""v0.11.0 契约测试: 交易成本 / T+1 / advise / factor category."""
import pytest
from datetime import date, timedelta
from core.schemas import Order, FactorValue
from tools.rebalance import (estimate_cost, CostModel, is_t_plus_1, can_close_today,
                              filter_orders_by_settlement, apply_cost_check,
                              build_rebalance_plan, Position, compute_target_weights,
                              RebalancePlan)


def test_cost_cn_ashare_sell_stamp():
    """A 股卖出印花税 0.05%"""
    o = Order(ticker="600519.SS", side="sell", qty=100, price=1000, order_type="limit")
    c = estimate_cost(o)
    notional = 100 * 1000
    # stamp = 0.0005 * 100000 = 50
    assert 45 <= c["stamp_and_fees"] <= 55
    # 滑点 5bps
    assert 45 <= c["slippage"] <= 55


def test_cost_cn_ashare_buy_no_stamp():
    o = Order(ticker="600519.SS", side="buy", qty=100, price=1000, order_type="limit")
    c = estimate_cost(o)
    assert c["stamp_and_fees"] == 0


def test_cost_us_zero_commission():
    o = Order(ticker="AAPL", side="buy", qty=100, price=200, order_type="limit")
    c = estimate_cost(o)
    assert c["commission"] == 0
    # 只有滑点 + SEC 费 (buy 无 sec)
    assert c["stamp_and_fees"] == 0


def test_is_t_plus_1():
    assert is_t_plus_1("600519.SS") is True
    assert is_t_plus_1("000858.SZ") is True
    assert is_t_plus_1("AAPL") is False
    assert is_t_plus_1("0700.HK") is False


def test_can_close_today_a_share():
    today = date(2026, 7, 18)
    assert can_close_today(today, "600519.SS", today) is False   # 当日买入不可卖
    assert can_close_today(today - timedelta(days=1), "600519.SS", today) is True
    assert can_close_today(today, "AAPL", today) is True         # T+0


def test_filter_orders_by_settlement():
    from tools.rebalance import Position
    today = date(2026, 7, 18)
    # 当天买的 A 股，要卖 → 应被拒
    pos = Position(ticker="600519.SS", qty=100, avg_cost=1000, market_price=1000)
    pos.open_date = today
    orders = [Order(ticker="600519.SS", side="sell", qty=100, price=1000, order_type="limit")]
    allowed, rejected = filter_orders_by_settlement(orders, {"600519.SS": pos}, today)
    assert len(rejected) == 1
    assert "T+1" in rejected[0][1]


def test_apply_cost_check_drops_high_cost():
    """成本超阈值订单应被丢弃。"""
    dec_price = 100
    # 造一个成本约 ~10bps 的单
    orders = [
        Order(ticker="600519.SS", side="sell", qty=100, price=100, order_type="limit"),  # ~10.5bps: 5 slip + 5 stamp
        Order(ticker="AAPL", side="buy", qty=1000, price=100, order_type="limit"),  # 5bps only
    ]
    plan = RebalancePlan(target_weights={}, current_weights={}, orders=orders, reasons=[], total_equity=100000)
    plan2 = apply_cost_check(plan, min_edge_bps=8.0)
    # A 股高成本被砍
    assert len(plan2.orders) == 1
    assert plan2.orders[0].ticker == "AAPL"


def test_factor_category_options():
    """options / microstructure 分类合法."""
    fv = FactorValue(name="iv_skew_real", value=0.05, category="options", used_data_ts=date.today())
    assert fv.category == "options"
    fv2 = FactorValue(name="ofi_5d", value=0.1, category="microstructure", used_data_ts=date.today())
    assert fv2.category == "microstructure"


def test_advise_cli_registered():
    src = open("manage.py").read()
    assert "cmd_advise" in src
    assert 'sub.add_parser("advise"' in src


def test_ab_sharpe_maxdd_present_in_result():
    """A/B _replay 输出 sharpe + max_drawdown key."""
    src = open("dashboard/server.py").read()
    assert '"sharpe"' in src
    assert '"max_drawdown"' in src


def test_options_factor_in_bundle_when_no_key():
    """无 options key 时，factor bundle 不 crash（因为 fetch_options_skew 返 None）."""
    from core.schemas import Bar, MarketData, Market
    from tools.factors import compute_factors
    from datetime import timedelta as _td
    bars = [Bar(date=date(2026,1,1)+_td(days=i), open=100, high=101, low=99, close=100+i*0.1, volume=1000000) for i in range(60)]
    md = MarketData(ticker="TESTX", market=Market.US, as_of=date(2026,1,1), source="test", bars=bars)
    fb = compute_factors(md)
    # 只是不 crash 即可
    assert len(fb.factors) > 0
