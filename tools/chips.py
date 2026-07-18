"""D2 ChipsAgent — 筹码分布/主力资金。A 股专用。"""
from __future__ import annotations
from core.schemas import MarketData, FactorBundle, AltSignal


def compute_chips(md: MarketData | None, alt: AltSignal | None) -> FactorBundle | None:
    if md is None:
        return None
    # 真实实现：210 日筹码累积、主力净流入、机构持股集中度
    return FactorBundle(ticker=md.ticker, as_of=md.as_of, factors=[], pit_verified=True)
