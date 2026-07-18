import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

_LLM_ENVS = (
    "OPENAI_API_KEY", "LLM_API_KEY", "DEEPSEEK_API_KEY", "ARK_API_KEY",
    "LLM_FALLBACK_KEY", "LLM_FALLBACK_BASE_URL", "LLM_PROFILE",
    "LLM_BASE_URL", "DEEP_LLM", "QUICK_LLM",
    "FALLBACK_DEEP_MODEL", "FALLBACK_QUICK_MODEL",
    "MOONSHOT_API_KEY", "DASHSCOPE_API_KEY", "VLLM_API_KEY",
)

@pytest.fixture(autouse=True)
def _clear_llm_env(monkeypatch):
    for k in _LLM_ENVS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_MAX_RETRIES", "0")
    monkeypatch.setenv("LLM_TIMEOUT_S", "5")
    yield
