"""v0.16.0: LLM 多提供商 fallback 链."""
import os
import pytest
from unittest.mock import patch


def _clear(monkeypatch):
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("LLM_TIMEOUT_S", "5")
    for k in ("OPENAI_API_KEY","LLM_API_KEY","DEEPSEEK_API_KEY","ARK_API_KEY",
             "LLM_FALLBACK_KEY","LLM_FALLBACK_BASE_URL","LLM_PROFILE",
             "LLM_BASE_URL","DEEP_LLM","QUICK_LLM",
             "FALLBACK_DEEP_MODEL","FALLBACK_QUICK_MODEL"):
        monkeypatch.delenv(k, raising=False)


def test_chain_default_has_three_providers(monkeypatch):
    _clear(monkeypatch)
    from agents_llm.llm_client import LLMClient
    c = LLMClient()
    names = [p.name for p in c.providers]
    assert len(c.providers) == 3
    assert names[0] == "openai"
    assert "deepseek-v4-pro" in names[1]
    assert "deepseek-v4-flash" in names[2]


def test_chain_uses_deepseek_key_for_fallbacks(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-deepseek")
    from agents_llm.llm_client import LLMClient
    c = LLMClient()
    assert c.providers[0].enabled is False
    assert c.providers[1].enabled is True
    assert c.providers[2].enabled is True
    assert c.providers[1].api_key == "sk-test-deepseek"
    assert c.providers[1].base_url == "https://api.deepseek.com/v1"
    assert c.providers[1].deep == "deepseek-v4-pro"
    assert c.providers[2].deep == "deepseek-v4-flash"


def test_llm_profile_disables_fallback_chain(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("LLM_PROFILE", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-only")
    from agents_llm.llm_client import LLMClient
    c = LLMClient()
    assert len(c.providers) == 1


def test_fallback_base_url_overridable(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-any")
    monkeypatch.setenv("LLM_FALLBACK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    from agents_llm.llm_client import LLMClient
    c = LLMClient()
    assert c.providers[1].base_url == "https://ark.cn-beijing.volces.com/api/v3"


@pytest.mark.asyncio
async def test_chain_falls_through_to_next_provider(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    from agents_llm.llm_client import LLMClient
    c = LLMClient()

    calls = []
    async def fake_post(self, payload):
        calls.append(self.name)
        if self.name == "openai":
            return {"__error__": "primary down"}
        return {"choices":[{"message":{"content":"ok"}}]}
    with patch.object(type(c.providers[0]), "_post", fake_post):
        r = await c.chat("deep","sys","user")
    assert r == "ok"
    assert calls == ["openai", "fallback1-deepseek-v4-pro"]


@pytest.mark.asyncio
async def test_chain_all_fail_returns_none(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
    from agents_llm.llm_client import LLMClient
    c = LLMClient()
    async def fake_post(self, payload):
        return {"__error__": "down"}
    with patch.object(type(c.providers[0]), "_post", fake_post):
        r = await c.chat("deep","sys","user")
    assert r is None
    audit = c.audit()
    assert len(audit) == 3
    assert all(a["ok"] is False for a in audit)


def test_enabled_true_if_any_provider_enabled(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    from agents_llm.llm_client import LLMClient
    c = LLMClient()
    assert c.enabled is True


def test_enabled_false_if_no_keys(monkeypatch):
    _clear(monkeypatch)
    from agents_llm.llm_client import LLMClient
    c = LLMClient()
    assert c.enabled is False
