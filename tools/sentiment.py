"""D2 SentimentAgent — 中文金融词典规则版 (可后续切换 LLM)."""
from __future__ import annotations
from datetime import date
from collections import Counter
from core.schemas import SentimentSignal, NewsItem


POS = {
    "涨": 1.0, "涨价": 1.5, "上调": 1.0, "利好": 1.5, "增长": 1.0, "增持": 1.2,
    "回购": 1.2, "分红": 0.8, "创新高": 1.5, "突破": 1.0, "超预期": 1.5,
    "订单": 0.8, "中标": 1.0, "签约": 0.8, "扩产": 1.0, "净利润增": 1.5,
    "上市": 0.5, "机构调研": 0.5, "看好": 1.0, "买入": 1.2, "推荐": 0.8,
    "受益": 0.8, "反弹": 0.6, "转好": 0.8,
}
NEG = {
    "跌": -1.0, "下跌": -1.0, "下调": -1.0, "利空": -1.5, "减持": -1.2,
    "亏损": -1.5, "退市": -2.0, "ST": -2.0, "警示": -1.0, "问询": -0.8,
    "违规": -1.5, "处罚": -1.5, "立案": -2.0, "调查": -1.0, "诉讼": -1.0,
    "商誉减值": -1.5, "计提": -1.0, "破发": -1.0, "解禁": -0.5,
    "抛售": -1.0, "减产": -0.8, "低于预期": -1.2, "折价": -0.6, "承压": -0.6,
}

TOPIC_KEYWORDS = {
    "涨价/降价": ["涨价", "下调", "上调", "调价", "提价"],
    "分红回购": ["分红", "回购", "派息", "权益分派"],
    "并购重组": ["并购", "重组", "收购", "换股"],
    "机构动作": ["机构调研", "增持", "减持", "举牌", "大宗交易"],
    "业绩": ["业绩", "净利润", "营收", "预告", "预增", "预减"],
    "监管": ["问询", "立案", "违规", "警示", "处罚"],
    "产品动态": ["新品", "发布", "上市", "扩产", "投产"],
}


def _score_one(text: str) -> float:
    s = 0.0
    for kw, v in POS.items():
        if kw in text:
            s += v
    for kw, v in NEG.items():
        if kw in text:
            s += v
    return s


def _extract_topics(items: list[NewsItem]) -> list[str]:
    counts: Counter[str] = Counter()
    for it in items:
        text = (it.title or "") + " " + (it.body or "")
        for topic, kws in TOPIC_KEYWORDS.items():
            if any(kw in text for kw in kws):
                counts[topic] += 1
    return [t for t, _ in counts.most_common(5)]


async def score_news(ticker: str, as_of: date, news: list[NewsItem]) -> SentimentSignal:
    if not news:
        return SentimentSignal(ticker=ticker, as_of=as_of, score=0.0, volume=0,
                               top_topics=[], news_used=[])

    weighted = 0.0
    weight_sum = 0.0
    from datetime import datetime as _dt
    now_dt = _dt.combine(as_of, _dt.min.time())
    for n in news:
        text = (n.title or "") + " " + (n.body or "")
        raw = _score_one(text)
        # 时间衰减：越近权重越大
        days_ago = max(0, (now_dt - n.ts).days)
        w = 1.0 / (1.0 + days_ago * 0.3)
        # 公告权重比新闻更高
        if n.source == "公告":
            w *= 1.5
        weighted += raw * w
        weight_sum += w

    # 归一化到 [-1, 1]：用 tanh 平滑
    import math
    if weight_sum > 0:
        avg = weighted / weight_sum
        score = math.tanh(avg / 2.0)
    else:
        score = 0.0

    return SentimentSignal(
        ticker=ticker, as_of=as_of,
        score=round(score, 3),
        volume=len(news),
        top_topics=_extract_topics(news),
        news_used=news[:10],  # 保留 10 条，方便审计
    )


if __name__ == "__main__":
    import asyncio
    from datetime import date as _d
    from tools.news import fetch_news
    for tk in ("600519.SS", "000858.SZ"):
        n = asyncio.run(fetch_news(tk, _d.today(), days=14))
        sig = asyncio.run(score_news(tk, _d.today(), n))
        print(f"{tk} score={sig.score:+.3f} vol={sig.volume} topics={sig.top_topics}")
