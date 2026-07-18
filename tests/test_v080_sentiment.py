"""v0.8.0 契约测试: sentiment + notification template."""
from tools.investment_news import score_headline, enrich_sentiment, aggregate_sentiment
from tools.notify import format_notification


def test_score_headline_positive_cn():
    s = score_headline("茅台批价上涨 主力资金加仓")
    assert s > 0.2

def test_score_headline_negative_cn():
    s = score_headline("公司被立案调查 遭双开处分")
    assert s < -0.2

def test_score_headline_neutral():
    s = score_headline("公司公告下周召开股东大会")
    assert -0.2 <= s <= 0.2

def test_enrich_labels():
    items = [{"title":"A股大涨 主力抢筹","summary":""},
             {"title":"业绩暴雷 立案","summary":""}]
    r = enrich_sentiment(items)
    assert r[0]["sentiment_label"] == "positive"
    assert r[1]["sentiment_label"] == "negative"

def test_aggregate_by_ticker():
    items = [{"title":"600519 利好","tickers":["600519.SS"]},
             {"title":"600519 遭调查","tickers":["600519.SS"]}]
    items = enrich_sentiment(items)
    agg = aggregate_sentiment(items, tickers=["600519.SS"])
    assert "600519.SS" in agg
    assert agg["600519.SS"]["count"] == 2

def test_format_notification():
    out = format_notification("test", {"决策":"a","风险":["r1","r2"]})
    assert "🎯" in out and "⚠️" in out
    assert "- r1" in out and "- r2" in out
