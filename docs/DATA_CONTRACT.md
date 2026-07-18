# Data Contract — Pydantic v2 Schemas

所有 Agent 间流转的数据统一走这套 schema。任何 Agent 必须校验输入 & 校验输出。

\`\`\`python
# core/schemas.py
from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


# ---------- 基础枚举 ----------
class Market(str, Enum):
    A_SS = "SS"      # 上交所
    A_SZ = "SZ"      # 深交所
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
    STALE = "stale"        # 数据超时但仍可用
    DEGRADED = "degraded"  # 降级源
    MISSING = "missing"


# ---------- D1 数据面 ----------
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
    as_of: date          # Point-in-Time 锚点
    bars: list[Bar]
    source: str          # tickflow / akshare / baostock / yfinance
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
    score: float = Field(ge=-1.0, le=1.0)  # -1 极负 → +1 极正
    volume: int                             # 讨论量
    top_topics: list[str] = []
    news_used: list[NewsItem] = []


class AltSignal(BaseModel):
    ticker: str
    as_of: date
    lhb_net_buy: Optional[float] = None       # 龙虎榜净买
    block_trade_amount: Optional[float] = None
    institution_hold_change: Optional[float] = None
    limit_up_reason: Optional[str] = None
    macro_regime: Optional[str] = None        # risk_on / risk_off / neutral


# ---------- D2 特征面 ----------
class FactorValue(BaseModel):
    name: str
    value: float
    category: Literal["price_volume", "fundamental", "sentiment", "event", "chips"]
    used_data_ts: date       # 用到的最新数据日期，用于未来函数守卫
    ic_hint: Optional[float] = None


class FactorBundle(BaseModel):
    ticker: str
    as_of: date
    factors: list[FactorValue]
    pit_verified: bool = False   # Point-in-Time 校验通过


# ---------- D3 策略面 ----------
class AnalystVerdict(BaseModel):
    analyst: Literal["fundamental", "technical", "sentiment", "macro_event"]
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    key_points: list[str]          # 3~5 条关键论据
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
    risks: list[str]             # 强制非空，防止只看多
    catalysts: list[str] = []
    checklist: list[str] = []    # 操作检查清单
    used_analysts: list[str]
    used_memory_refs: list[str] = []


# ---------- D4 回测面 ----------
class BacktestMetrics(BaseModel):
    ticker: str
    period: tuple[date, date]
    total_return: float
    annual_return: float
    sharpe: float
    max_drawdown: float
    win_rate: float
    turnover: float
    alpha_vs_benchmark: float
    attribution: dict[str, float] = {}  # 因子/行业归因


# ---------- D5 风控面 ----------
class RiskCheckResult(BaseModel):
    level: Literal["order", "portfolio", "strategy", "compliance"]
    passed: bool
    reasons: list[str] = []
    forced_action: Optional[Literal["block", "downsize", "warn"]] = None


class RiskReport(BaseModel):
    ticker: str
    checks: list[RiskCheckResult]
    final_action: Literal["pass", "downsize", "block"]


# ---------- D6 执行面 ----------
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


# ---------- D8 记忆面 ----------
class MemoryRecord(BaseModel):
    ticker: str
    decision_ts: datetime
    decision: Decision
    realized_return: Optional[float] = None      # T+N 后回填
    alpha_vs_benchmark: Optional[float] = None
    reflection: Optional[str] = None
\`\`\`

## 契约变更规则

- **禁止破坏性变更**：任何字段删除或类型变更需 major version bump。
- **新增字段**：需带默认值，向后兼容。
- **Decision.risks 非空**：从设计层面强制 LLM 输出风险，防止"永远看多"。
- **FactorBundle.pit_verified**：任何进入策略层的因子必须通过 PIT 校验，否则 Orchestrator 拦截。
