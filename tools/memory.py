"""D8 MemoryAgent + 索引 — 简易 JSON 存储。"""
from __future__ import annotations
import json, os
from datetime import date, datetime
from core.schemas import Decision, MemoryRecord

MEM_DIR = os.path.join(os.path.dirname(__file__), "..", "memory", "decisions")


def query_memory(ticker: str, k: int = 3) -> list[MemoryRecord]:
    p = os.path.join(MEM_DIR, ticker)
    if not os.path.isdir(p):
        return []
    files = sorted(os.listdir(p))
    out: list[MemoryRecord] = []
    for f in files[-k*3:]:
        fp = os.path.join(p, f)
        try:
            with open(fp) as fh:
                txt = fh.read().strip()
            if not txt:
                continue
            out.append(MemoryRecord.model_validate_json(txt))
        except Exception:
            continue
    return out[-k:]


def write_memory(dec: Decision | None) -> None:
    if dec is None:
        return
    rec = MemoryRecord(ticker=dec.ticker, decision_ts=datetime.utcnow(), decision=dec)
    p = os.path.join(MEM_DIR, dec.ticker)
    os.makedirs(p, exist_ok=True)
    fname = f"{dec.as_of.isoformat()}.json"
    with open(os.path.join(p, fname), "w") as fh:
        fh.write(rec.model_dump_json(indent=2))
