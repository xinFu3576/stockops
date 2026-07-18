"""统一 LLM 客户端 · 多提供商 fallback 链 (v0.16)

优先级 (第一个 enabled 且未 fail 的胜出):
  1) primary   → OpenAI GPT     (env: OPENAI_API_KEY 或 LLM_API_KEY，兼容 LLM_BASE_URL)
  2) fallback1 → 火山方舟 DeepSeek v4 pro   (env: ARK_API_KEY 或 LLM_ARK_KEY)
  3) fallback2 → 火山方舟 DeepSeek v4 flash (env: ARK_API_KEY 或 LLM_ARK_KEY)

任一 provider 的 structured/chat 调用返回 None 时，自动降级到下一个 provider。
所有 provider 都失败则返回 None，由调用方走启发式兜底。

兼容旧配置：
  LLM_PROFILE=openai|deepseek|kimi|qwen|ark|vllm  → 只用该单一 profile
  LLM_BASE_URL / LLM_API_KEY / DEEP_LLM / QUICK_LLM 仍生效（覆盖 primary）
"""
from __future__ import annotations
import json, os, asyncio
from typing import Any, Type, TypeVar
from pydantic import BaseModel, ValidationError
import httpx

T = TypeVar("T", bound=BaseModel)


PROFILES = {
    "openai":    {"base_url": "https://api.openai.com/v1",
                  "deep": "gpt-4o", "quick": "gpt-4o-mini",
                  "key_env": "OPENAI_API_KEY"},
    "deepseek":  {"base_url": "https://api.deepseek.com/v1",
                  "deep": "deepseek-chat", "quick": "deepseek-chat",
                  "key_env": "DEEPSEEK_API_KEY"},
    "kimi":      {"base_url": "https://api.moonshot.cn/v1",
                  "deep": "moonshot-v1-32k", "quick": "moonshot-v1-8k",
                  "key_env": "MOONSHOT_API_KEY"},
    "qwen":      {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                  "deep": "qwen-max", "quick": "qwen-turbo",
                  "key_env": "DASHSCOPE_API_KEY"},
    "ark":       {"base_url": "https://ark.cn-beijing.volces.com/api/v3",
                  "deep": "doubao-1-5-pro-32k-250115", "quick": "doubao-1-5-lite-32k-250115",
                  "key_env": "ARK_API_KEY"},
    "vllm":      {"base_url": os.getenv("VLLM_BASE_URL","http://127.0.0.1:8000/v1"),
                  "deep": os.getenv("VLLM_MODEL","local"), "quick": os.getenv("VLLM_MODEL","local"),
                  "key_env": "VLLM_API_KEY"},
}


class _Provider:
    """单个 LLM 后端 (base_url + api_key + model names)。"""
    def __init__(self, name: str, base_url: str, api_key: str,
                 deep: str, quick: str, timeout: float, retries: int):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.deep = deep
        self.quick = quick
        self.timeout = timeout
        self.retries = retries

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _model(self, tier: str) -> str:
        return self.deep if tier == "deep" else self.quick

    async def _post(self, payload: dict) -> dict | None:
        headers = {"Authorization": f"Bearer {self.api_key}",
                   "Content-Type": "application/json"}
        last_err = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=True) as c:
                    r = await c.post(f"{self.base_url}/chat/completions",
                                     json=payload, headers=headers)
                    r.raise_for_status()
                    return r.json()
            except (httpx.HTTPError, KeyError) as e:
                last_err = e
                await asyncio.sleep(0.4 * (attempt + 1))
        return {"__error__": str(last_err)[:160]}

    async def structured(self, tier, system, user, schema):
        if not self.enabled:
            return None
        model = self._model(tier)
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        sys_prompt = (
            f"{system}\n\n"
            f"你必须只输出一个 JSON 对象，严格符合以下 JSON Schema：\n{schema_json}\n"
            f"不要输出任何解释、markdown 代码块围栏或多余字段。"
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        js = await self._post(payload)
        if not js or js.get("__error__"):
            return None
        try:
            content = js["choices"][0]["message"]["content"]
            return schema.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValidationError, KeyError):
            return None

    async def chat(self, tier, system, user, temperature=0.4, max_tokens=400):
        if not self.enabled:
            return None
        model = self._model(tier)
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        js = await self._post(payload)
        if not js or js.get("__error__"):
            return None
        try:
            return (js["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, TypeError):
            return None


class LLMClient:
    """带 fallback 链的 LLM 门面。"""

    def __init__(self):
        self.timeout = float(os.getenv("LLM_TIMEOUT_S", "40"))
        self.retries = int(os.getenv("LLM_MAX_RETRIES", "2"))
        self._audit: list[dict] = []

        prof_name = os.getenv("LLM_PROFILE", "").lower()

        # --- Primary: OpenAI GPT (被 LLM_PROFILE 强制时改为该 profile) ---
        primary_profile = PROFILES.get(prof_name) if prof_name else PROFILES["openai"]
        primary_base = os.getenv("LLM_BASE_URL") or primary_profile["base_url"]
        primary_key = (os.getenv("LLM_API_KEY")
                       or os.getenv(primary_profile["key_env"])
                       or os.getenv("OPENAI_API_KEY", ""))
        primary_deep = os.getenv("DEEP_LLM") or primary_profile["deep"]
        primary_quick = os.getenv("QUICK_LLM") or primary_profile["quick"]
        primary = _Provider(
            name=prof_name or "openai",
            base_url=primary_base, api_key=primary_key,
            deep=primary_deep, quick=primary_quick,
            timeout=self.timeout, retries=self.retries,
        )

        providers = [primary]

        # --- Fallback 只在未强制 LLM_PROFILE 时启用 ---
        if not prof_name:
            # Fallback 默认走 DeepSeek 官方 API (api.deepseek.com)
            # 因为 deepseek-v4-pro / deepseek-v4-flash 是 DeepSeek 平台模型；
            # 若拿到真的方舟 key，可用 LLM_FALLBACK_BASE_URL 覆盖到 ark.cn-beijing.volces.com/api/v3
            fb_base = os.getenv("LLM_FALLBACK_BASE_URL",
                                "https://api.deepseek.com/v1")
            fb_key = (os.getenv("LLM_FALLBACK_KEY")
                       or os.getenv("DEEPSEEK_API_KEY")
                       or os.getenv("ARK_API_KEY", ""))
            fb_deep = os.getenv("FALLBACK_DEEP_MODEL",  "deepseek-v4-pro")
            fb_flash = os.getenv("FALLBACK_QUICK_MODEL", "deepseek-v4-flash")
            fb1 = _Provider(
                name="fallback1-deepseek-v4-pro",
                base_url=fb_base, api_key=fb_key,
                deep=fb_deep, quick=fb_deep,
                timeout=self.timeout, retries=self.retries,
            )
            fb2 = _Provider(
                name="fallback2-deepseek-v4-flash",
                base_url=fb_base, api_key=fb_key,
                deep=fb_flash, quick=fb_flash,
                timeout=self.timeout, retries=self.retries,
            )
            providers.extend([fb1, fb2])

        self.providers = providers
        self.profile_name = prof_name or "chain(gpt->ark-pro->ark-flash)"

        # 向后兼容属性
        self.base_url = primary.base_url
        self.api_key = primary.api_key
        self.deep = primary.deep
        self.quick = primary.quick

    @property
    def enabled(self) -> bool:
        return any(p.enabled for p in self.providers)

    def _model(self, tier):
        for p in self.providers:
            if p.enabled:
                return p._model(tier)
        return "unknown"

    async def structured(self, tier, system, user, schema):
        for p in self.providers:
            if not p.enabled:
                continue
            result = await p.structured(tier, system, user, schema)
            if result is not None:
                self._audit.append({"provider": p.name, "model": p._model(tier),
                                    "tier": tier, "ok": True})
                return result
            self._audit.append({"provider": p.name, "model": p._model(tier),
                                "tier": tier, "ok": False, "fallback": True})
        return None

    async def chat(self, tier, system, user, temperature=0.4, max_tokens=400):
        for p in self.providers:
            if not p.enabled:
                continue
            result = await p.chat(tier, system, user, temperature, max_tokens)
            if result is not None:
                self._audit.append({"provider": p.name, "model": p._model(tier),
                                    "tier": tier, "kind": "chat", "ok": True})
                return result
            self._audit.append({"provider": p.name, "model": p._model(tier),
                                "tier": tier, "kind": "chat", "ok": False, "fallback": True})
        return None

    def audit(self):
        return self._audit


client = LLMClient()
