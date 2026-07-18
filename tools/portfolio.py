"""D5-b Portfolio 层 — 行业敞口 + 相关性 约束。

输入：多标的的 Order 列表 + 各标的 F10 sector（如有）+ 最近 60 日收益
输出：调整后 Order 列表 + 违规报告
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
import numpy as np
import pandas as pd

from core.schemas import Order, MarketData


MAX_INDUSTRY_WEIGHT = 0.30   # 单行业总敞口
MAX_CORR_CLUSTER_WEIGHT = 0.40  # 相关系数 > 0.8 的一组，总敞口
CORR_THRESHOLD = 0.8


@dataclass
class PortfolioAdjust:
    orders: list[Order]
    violations: list[str]
    industry_weights: dict[str, float]


def _order_weight(o: Order, account: float) -> float:
    if not o.price or not o.qty:
        return 0.0
    return (o.price * o.qty) / account


def _corr_matrix(mds: dict[str, MarketData]) -> pd.DataFrame:
    frames = {}
    for tk, md in mds.items():
        rets = []
        for i in range(1, len(md.bars)):
            p0, p1 = md.bars[i-1].close, md.bars[i].close
            if p0 > 0:
                rets.append(p1 / p0 - 1)
        frames[tk] = pd.Series(rets[-60:]) if rets else pd.Series(dtype=float)
    if not frames:
        return pd.DataFrame()
    df = pd.DataFrame(frames).dropna()
    if len(df) < 20:
        return pd.DataFrame()
    return df.corr()


def _corr_clusters(corr: pd.DataFrame) -> list[list[str]]:
    """简单联通分量：|corr|>阈值 视为同类。"""
    if corr.empty:
        return []
    seen: set[str] = set()
    clusters: list[list[str]] = []
    for a in corr.columns:
        if a in seen:
            continue
        stack = [a]; cluster: list[str] = []
        while stack:
            x = stack.pop()
            if x in seen: continue
            seen.add(x); cluster.append(x)
            for b in corr.columns:
                if b not in seen and abs(corr.loc[x, b]) >= CORR_THRESHOLD:
                    stack.append(b)
        clusters.append(cluster)
    return clusters


def rebalance(orders: list[Order],
              mds: dict[str, MarketData],
              sectors: dict[str, str | None],
              account: float = 100_000.0) -> PortfolioAdjust:
    violations: list[str] = []
    if not orders:
        return PortfolioAdjust(orders=[], violations=[], industry_weights={})

    # 1) 行业敞口
    ind_weight: dict[str, float] = defaultdict(float)
    for o in orders:
        sec = sectors.get(o.ticker) or "未知"
        ind_weight[sec] += _order_weight(o, account)

    scale = {sec: 1.0 for sec in ind_weight}
    for sec, w in ind_weight.items():
        if w > MAX_INDUSTRY_WEIGHT:
            scale[sec] = MAX_INDUSTRY_WEIGHT / w
            violations.append(f"[行业] {sec} 敞口 {w:.1%} > {MAX_INDUSTRY_WEIGHT:.0%}，按 {scale[sec]:.2f} 缩容")

    # 2) 相关性集群
    corr = _corr_matrix(mds)
    clusters = _corr_clusters(corr)
    cluster_scale: dict[str, float] = {}
    for cl in clusters:
        if len(cl) <= 1:
            continue
        w = sum(_order_weight(o, account) for o in orders if o.ticker in cl)
        if w > MAX_CORR_CLUSTER_WEIGHT:
            f = MAX_CORR_CLUSTER_WEIGHT / w
            for tk in cl:
                cluster_scale[tk] = min(cluster_scale.get(tk, 1.0), f)
            violations.append(f"[相关性] 集群 {cl} 合计敞口 {w:.1%} > {MAX_CORR_CLUSTER_WEIGHT:.0%}，按 {f:.2f} 缩容")

    # 3) 应用缩放（行业 × 集群，取更严）
    new_orders: list[Order] = []
    for o in orders:
        sec = sectors.get(o.ticker) or "未知"
        f = min(scale.get(sec, 1.0), cluster_scale.get(o.ticker, 1.0))
        if f >= 0.999:
            new_orders.append(o)
            continue
        new_qty = int(o.qty * f)
        if o.ticker.upper().endswith((".SS", ".SH", ".SZ")):
            new_qty = (new_qty // 100) * 100
        if new_qty > 0:
            new_orders.append(Order(
                ticker=o.ticker, side=o.side, qty=new_qty, price=o.price,
                order_type=o.order_type, tag=(o.tag or "") + f"_scaled_{f:.2f}",
            ))

    return PortfolioAdjust(orders=new_orders, violations=violations,
                           industry_weights=dict(ind_weight))
