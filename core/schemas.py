# core/schemas.py
# Pydantic v2 schemas — see docs/DATA_CONTRACT.md for full description.
from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


class Market(str, Enum):
    A_SS = "SS"
    A_SZ = "SZ"
    HK = "HK"
    US = "US"


class Direction(str, Enum):
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class Health(str, Enum):
    OK = "ok"
    STALE = "stale"
    DEGRADED = "degraded"
    MISSING = "missing"


class Bar(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: Optional[float] = None
    turnover: Optional[float] = None
    adj_factor: float = 1.0
    halted: bool = False


class MarketData(BaseModel):
    ticker: str
    market: Market
    as_of: date
    bars: list[Bar]
    source: str
    health: Health = Health.OK


class NewsItem(BaseModel):
    ts: datetime
    title: str
    url: Optional[str] = None
    source: str
    body: Optional[str] = None
    lang: Literal["zh", "en"] = "zh"


class SentimentSignal(BaseModel):
    ticker: str
    as_of: date
    score: float = Field(ge=-1.0, le=1.0)
    volume: int
    top_topics: list[str] = []
    news_used: list[NewsItem] = []


class AltSignal(BaseModel):
    ticker: str
    as_of: date
    lhb_net_buy: Optional[float] = None
    block_trade_amount: Optional[float] = None
    institution_hold_change: Optional[float] = None
    limit_up_reason: Optional[str] = None
    macro_regime: Optional[str] = None


class FactorValue(BaseModel):
    name: str
    value: float
    category: Literal["price_volume", "fundamental", "sentiment", "event", "chips", "microstructure", "options"]
    used_data_ts: date
    ic_hint: Optional[float] = None


class FactorBundle(BaseModel):
    ticker: str
    as_of: date
    factors: list[FactorValue]
    pit_verified: bool = False


class AnalystVerdict(BaseModel):
    analyst: Literal["fundamental", "technical", "sentiment", "macro_event", "portfolio_view"]
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    key_points: list[str]
    risks: list[str] = []
    catalysts: list[str] = []
    horizon_days: int = 20


class DebateTurn(BaseModel):
    side: Literal["bull", "bear"]
    round: int
    argument: str
    references_verdicts: list[str] = []


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str
    as_of: date
    direction: Direction
    score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0.0, le=1.0)
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    horizon_days: int = 20
    key_points: list[str]
    risks: list[str] = Field(min_length=1)  # 强制风险非空
    catalysts: list[str] = []
    checklist: list[str] = []
    used_analysts: list[str]
    used_memory_refs: list[str] = []


class BacktestMetrics(BaseModel):
    ticker: str
    period_start: date
    period_end: date
    total_return: float
    annual_return: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    turnover: float
    alpha_vs_benchmark: float
    attribution: dict[str, float] = {}


class RiskCheckResult(BaseModel):
    level: Literal["order", "portfolio", "strategy", "compliance"]
    passed: bool
    reasons: list[str] = []
    forced_action: Optional[Literal["block", "downsize", "warn"]] = None


class RiskReport(BaseModel):
    ticker: str
    checks: list[RiskCheckResult]
    final_action: Literal["pass", "downsize", "block"]


class Order(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    qty: int
    price: Optional[float] = None
    order_type: Literal["market", "limit"] = "limit"
    valid_until: Optional[datetime] = None
    tag: Optional[str] = None


class Fill(BaseModel):
    order_ref: str
    filled_qty: int
    avg_price: float
    ts: datetime
    mode: Literal["dry_run", "paper", "live"]


class MemoryRecord(BaseModel):
    ticker: str
    decision_ts: datetime
    decision: Decision
    realized_return: Optional[float] = None
    alpha_vs_benchmark: Optional[float] = None
    reflection: Optional[str] = None
