"""v0.15.0: broker ibkr/futu 执行 + i18n + debate 冲突分 + 知识库."""
import asyncio, os
import pytest
from datetime import date
from unittest.mock import patch


def test_execute_advise_orders_supports_ibkr(monkeypatch, tmp_path):
    """--execute ibkr 应能实例化 IBKRPaperBroker (即便下不了单)。"""
    from tools.advise_pipeline import execute_advise_orders
    from core.schemas import Order
    # 空 orders → count=0，不 crash
    r = asyncio.run(execute_advise_orders([], broker="ibkr"))
    assert r["count"] == 0


def test_execute_advise_orders_supports_futu():
    from tools.advise_pipeline import execute_advise_orders
    r = asyncio.run(execute_advise_orders([], broker="futu"))
    assert r["count"] == 0


def test_execute_advise_orders_unknown_broker():
    from tools.advise_pipeline import execute_advise_orders
    r = asyncio.run(execute_advise_orders([], broker="unknown"))
    assert "error" in r or r["count"] == 0


def test_i18n_dict_en_and_zh():
    from tools.advise_pipeline import _I18N, _t
    assert "zh" in _I18N and "en" in _I18N
    assert _t("en", "title").startswith("🎯 StockOps")
    assert "SELL" in _t("en", "action")["sell"]
    assert "买入" in _t("zh", "action")["buy"]


def test_run_advise_lang_param_signature():
    """run_advise 接受 lang 参数。"""
    import inspect
    from tools.advise_pipeline import run_advise
    sig = inspect.signature(run_advise)
    assert "lang" in sig.parameters


def test_compute_conflict_score_high():
    from agents_llm.debate import compute_conflict_score
    from core.schemas import AnalystVerdict, Direction
    from core.orchestrator import AgentState
    st = AgentState(ticker="AAPL", as_of=date(2026,1,1), mode="dry_run")
    st.verdicts = {
        "technical": AnalystVerdict(analyst="technical", direction=Direction.STRONG_BUY, confidence=0.7,
                                    key_points=["up"], risks=["r"], catalysts=[]),
        "fundamental": AnalystVerdict(analyst="fundamental", direction=Direction.STRONG_SELL, confidence=0.7,
                                       key_points=["down"], risks=["r"], catalysts=[]),
    }
    r = compute_conflict_score(st)
    assert r["conflict_score"] >= 60
    assert r["bulls"] == 1 and r["bears"] == 1


def test_compute_conflict_score_low():
    from agents_llm.debate import compute_conflict_score
    from core.schemas import AnalystVerdict, Direction
    from core.orchestrator import AgentState
    st = AgentState(ticker="AAPL", as_of=date(2026,1,1), mode="dry_run")
    st.verdicts = {
        "technical": AnalystVerdict(analyst="technical", direction=Direction.BUY, confidence=0.6,
                                    key_points=["kp"], risks=["r"], catalysts=[]),
        "fundamental": AnalystVerdict(analyst="fundamental", direction=Direction.BUY, confidence=0.6,
                                       key_points=["kp"], risks=["r"], catalysts=[]),
    }
    r = compute_conflict_score(st)
    assert r["conflict_score"] < 40


def test_synthesize_debate():
    from agents_llm.debate import synthesize_debate
    from core.schemas import DebateTurn
    turns = [
        DebateTurn(side="bull", round=1, argument="a"*200, references_verdicts=["technical"]),
        DebateTurn(side="bear", round=1, argument="b"*200, references_verdicts=["fundamental"]),
    ]
    s = synthesize_debate(turns, {"conflict_score": 70})
    assert s["high_conflict"] is True
    assert "bull_summary" in s


def test_kb_write_local(tmp_path, monkeypatch):
    import tools.knowledge_base as kb
    monkeypatch.setattr(kb, "KB_DIR", tmp_path / "kb")
    fp = kb.write_local(date(2026, 3, 15), "# title\n\ncontent")
    assert (tmp_path / "kb" / "2026" / "03" / "2026-03-15.md").exists()
    assert (tmp_path / "kb" / "INDEX.md").exists()


def test_archive_daily_advise_local_only(tmp_path, monkeypatch):
    import tools.knowledge_base as kb
    monkeypatch.setattr(kb, "KB_DIR", tmp_path / "kb")
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("CONFLUENCE_TOKEN", raising=False)
    monkeypatch.delenv("GH_KB_REPO", raising=False)
    r = kb.archive_daily_advise(date(2026, 3, 15), "# hello",
                                exec_results=[{"ticker":"AAPL","side":"buy","qty":100,
                                               "price":200,"status":"filled"}])
    assert "local" in r
    fp = pathlib.Path(r["local"])
    body = fp.read_text()
    assert "执行结果" in body
    assert "filled" in body


def test_kb_notion_needs_token(monkeypatch):
    import tools.knowledge_base as kb
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    r = kb.write_notion(date.today(), "t", "body")
    assert not r["ok"]


def test_daily_sh_has_archive():
    src = open("daily.sh").read()
    assert "--archive" in src
    assert "reports/kb" in src


def test_advise_execute_safety_gate_downgrades():
    """--execute ibkr 无 --i-accept-real-money 应降到 paper (通过检查代码存在)。"""
    src = open("manage.py").read()
    assert "SAFETY" in src and "强制降级到 paper" in src


import pathlib
