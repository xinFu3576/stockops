"""经纪商适配层 (broker adapters).

Interface: 每个 broker 实现 place_order(order: OrderIntent) -> OrderResult。
提供:
  DryRunBroker(默认)
  PaperBroker(本地虚拟撮合)
  IBKRPaperBroker(需 ib-insync + gateway)
  FutuPaperBroker(需 futu-api + opend)
"""
from __future__ import annotations
from .base import Broker, OrderResult
from .dryrun import DryRunBroker
from .paper import PaperBroker
from .ibkr import IBKRPaperBroker
from .futu import FutuPaperBroker


def get_broker(name: str) -> Broker:
    name = (name or "dry_run").lower()
    if name in ("dry_run", "dry", "dryrun"): return DryRunBroker()
    if name in ("paper", "sim"): return PaperBroker()
    if name in ("ibkr", "ibkr_paper"): return IBKRPaperBroker()
    if name in ("futu", "futu_paper"): return FutuPaperBroker()
    raise ValueError(f"unknown broker: {name}")
