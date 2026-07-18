"""
Orchestrator — LangGraph 状态机骨架

真实项目请 pip install langgraph；此处给可运行的最小演示版，
接口保持与 LangGraph 兼容，方便后续替换。
"""
from __future__ import annotations
import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from core.schemas import (
    MarketData, SentimentSignal, AltSignal, FactorBundle,
    AnalystVerdict, DebateTurn, Decision, RiskReport, Order, Fill,
    BacktestMetrics, MemoryRecord,
)


# ---------- AgentState ----------
@dataclass
class AgentState:
    ticker: str
    as_of: date
    mode: str = "dry_run"       # dry_run | paper | live

    market_data: MarketData | None = None
    news_raw: list[Any] = field(default_factory=list)
    alt_signals: AltSignal | None = None
    fundamentals: dict | None = None

    factor_bundle: FactorBundle | None = None
    sentiment_signal: SentimentSignal | None = None
    chips_bundle: FactorBundle | None = None

    verdicts: dict[str, AnalystVerdict] = field(default_factory=dict)
    debate: list[DebateTurn] = field(default_factory=list)
    memory_refs: list[MemoryRecord] = field(default_factory=list)

    decision: Decision | None = None
    backtest: BacktestMetrics | None = None
    risk: RiskReport | None = None
    orders: list[Order] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)

    report: str = ""
    trace: list[dict] = field(default_factory=list)


# ---------- Node registry ----------
Node = Callable[[AgentState], "asyncio.Future[AgentState] | AgentState"]
NODES: dict[str, Node] = {}

def node(name: str):
    def deco(fn: Node) -> Node:
        NODES[name] = fn
        return fn
    return deco


# ---------- 交易日历闸门（示意） ----------
def is_trading_day(d: date, market: str = "A") -> bool:
    try:
        import akshare as ak
        cal = ak.tool_trade_date_hist_sina()
        return d.isoformat() in set(cal["trade_date"].astype(str).tolist())
    except Exception:
        # 兜底：只跳周末
        return d.weekday() < 5


# ---------- 骨架节点（真实实现里各自替换成 Agent 具体逻辑） ----------
@node("market_data")
async def n_market_data(s: AgentState) -> AgentState:
    from tools.market_data import fetch_market_data
    s.market_data = await fetch_market_data(s.ticker, s.as_of)
    return s

@node("news")
async def n_news(s: AgentState) -> AgentState:
    from tools.news import fetch_news
    s.news_raw = await fetch_news(s.ticker, s.as_of)
    return s

@node("alt_data")
async def n_alt(s: AgentState) -> AgentState:
    from tools.alt_data import fetch_alt
    s.alt_signals = await fetch_alt(s.ticker, s.as_of)
    return s

@node("fundamentals")
async def n_fund(s: AgentState) -> AgentState:
    from tools.fundamentals import fetch_fundamentals
    s.fundamentals = await fetch_fundamentals(s.ticker, s.as_of)
    return s

@node("factors")
async def n_factors(s: AgentState) -> AgentState:
    from tools.factors import compute_factors
    s.factor_bundle = compute_factors(s.market_data, s.fundamentals)
    return s

@node("sentiment_factor")
async def n_sent(s: AgentState) -> AgentState:
    from tools.sentiment import score_news
    s.sentiment_signal = await score_news(s.ticker, s.as_of, s.news_raw)
    return s

@node("chips")
async def n_chips(s: AgentState) -> AgentState:
    from tools.chips import compute_chips
    s.chips_bundle = compute_chips(s.market_data, s.alt_signals)
    return s

@node("analysts_parallel")
async def n_analysts(s: AgentState) -> AgentState:
    from agents_llm import analysts
    results = await asyncio.gather(
        analysts.fundamental(s), analysts.technical(s),
        analysts.sentiment(s), analysts.macro_event(s),
    )
    for v in results:
        s.verdicts[v.analyst] = v
    return s

@node("debate")
async def n_debate(s: AgentState) -> AgentState:
    from agents_llm import debate
    s.debate = await debate.run(s, max_rounds=2)
    return s

@node("research_manager")
async def n_rm(s: AgentState) -> AgentState:
    from agents_llm import research_manager
    from tools.memory import query_memory
    s.memory_refs = query_memory(s.ticker, k=3)
    s.decision = await research_manager.decide(s)
    return s

@node("backtest")
async def n_backtest(s: AgentState) -> AgentState:
    from tools.backtest import run_backtest
    s.backtest = run_backtest(s.decision, s.market_data)
    return s

@node("risk")
async def n_risk(s: AgentState) -> AgentState:
    from tools.risk import check_risk
    s.risk = await check_risk(s.decision, s.market_data, portfolio=None)
    return s

@node("trader")
async def n_trader(s: AgentState) -> AgentState:
    from agents_llm import trader
    if s.risk and s.risk.final_action != "block":
        s.orders = await trader.build_orders(s)
    return s

@node("execution")
async def n_exec(s: AgentState) -> AgentState:
    from tools.execution import execute
    s.fills = await execute(s.orders, mode=s.mode)
    return s

@node("report")
async def n_report(s: AgentState) -> AgentState:
    from agents_llm import reporting
    s.report = await reporting.render(s)
    return s

@node("persist")
async def n_persist(s: AgentState) -> AgentState:
    from tools.memory import write_memory
    write_memory(s.decision)
    return s


# ---------- 编排 ----------
PIPELINE = [
    ("market_data", "news", "alt_data", "fundamentals"),   # 并行组 1
    ("factors", "sentiment_factor", "chips"),  # 并行组 2
    ("analysts_parallel",),
    ("debate",),
    ("research_manager",),
    ("backtest",),
    ("risk",),
    ("trader",),
    ("execution",),
    ("report",),
    ("persist",),
]


async def run_one(ticker: str, as_of: date, mode: str = "dry_run",
                  force: bool = False) -> AgentState:
    if not force and not is_trading_day(as_of):
        print(f"[gate] {as_of} 非交易日，短路")
        return AgentState(ticker=ticker, as_of=as_of, mode=mode)

    s = AgentState(ticker=ticker, as_of=as_of, mode=mode)
    for group in PIPELINE:
        coros = [NODES[name](s) for name in group]
        results = await asyncio.gather(*coros, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                s.trace.append({"error": str(r)})
                # 真实项目在此写入 checkpoint 并按策略降级/重试
    return s




# ---------- 批量入口：跨标的 Portfolio 约束 ----------
async def run_batch(tickers: list[str], as_of: date, mode: str = "dry_run",
                    force: bool = False) -> dict:
    """并发跑多标的 → Portfolio 层再平衡。"""
    from tools.portfolio import rebalance
    states = await asyncio.gather(*[
        run_one(t, as_of, mode, force) for t in tickers
    ])

    all_orders = []
    mds = {}
    sectors: dict[str, str | None] = {}
    for st in states:
        all_orders.extend(st.orders)
        if st.market_data:
            mds[st.ticker] = st.market_data
        sec = None
        if st.fundamentals:
            sec = st.fundamentals.get("sector")
        sectors[st.ticker] = sec

    adjust = rebalance(all_orders, mds, sectors)
    return {
        "states": states,
        "orders_before": all_orders,
        "orders_after": adjust.orders,
        "violations": adjust.violations,
        "industry_weights": adjust.industry_weights,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", required=True, help="逗号分隔")
    ap.add_argument("--date", required=True)
    ap.add_argument("--mode", default="dry_run",
                    choices=["dry_run", "paper", "live"])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--i-accept-real-money", action="store_true",
                    help="切换到 paper/live 前必须显式声明,否则强制降级到 dry_run")
    args = ap.parse_args()

    if args.mode != "dry_run" and not getattr(args, "i_accept_real_money", False):
        print(f"[SAFETY] --mode={args.mode} 未附带 --i-accept-real-money,强制降级到 dry_run")
        args.mode = "dry_run"

    as_of = date.fromisoformat(args.date)
    tickers = [t.strip() for t in args.tickers.split(",")]

    result = asyncio.run(run_batch(tickers, as_of, args.mode, args.force))
    for st in result["states"]:
        print(f"\n=== {st.ticker} @ {st.as_of} ({st.mode}) ===")
        if st.decision:
            print(st.decision.model_dump_json(indent=2))
        if st.report:
            print("\n--- Report ---\n" + st.report)
    if result["violations"]:
        print("\n=== 组合约束 ===")
        for v in result["violations"]:
            print("  " + v)
    if result["orders_after"] and result["orders_after"] != result["orders_before"]:
        print("\n=== 调整后订单 ===")
        for o in result["orders_after"]:
            print(f"  {o.ticker} {o.side} {o.qty}@{o.price} {o.tag}")


if __name__ == "__main__":
    main()
