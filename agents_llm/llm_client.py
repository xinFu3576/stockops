"""统一 LLM 客户端 — OpenAI 兼容协议 (含 DeepSeek/Kimi/通义/本地 vLLM)。

配置 (env)：
  LLM_BASE_URL      默认 https://api.openai.com/v1
  LLM_API_KEY       无 key 时全部走启发式兜底 (由调用方处理)
  DEEP_LLM          深度模型名 (研究经理/辩论/复盘)
  QUICK_LLM         轻量模型名 (情绪打分/摘要)
  LLM_MAX_RETRIES   默认 2
  LLM_TIMEOUT_S     默认 40
"""
from __future__ import annotations
import json, os, asyncio
from typing import Any, Type, TypeVar
from pydantic import BaseModel, ValidationError
import httpx

T = TypeVar("T", bound=BaseModel)


# 预设 profile:一行切换 LLM 后端
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


class LLMClient:
    def __init__(self):
        # profile 优先(LLM_PROFILE=ark),显式 LLM_BASE_URL/API_KEY 可覆盖
        prof_name = os.getenv("LLM_PROFILE", "").lower()
        prof = PROFILES.get(prof_name, {})
        self.base_url = (os.getenv("LLM_BASE_URL") or prof.get("base_url",
                         "https://api.openai.com/v1")).rstrip("/")
        key_env = prof.get("key_env", "LLM_API_KEY")
        self.api_key = os.getenv("LLM_API_KEY") or os.getenv(key_env, "")
        self.deep = os.getenv("DEEP_LLM") or prof.get("deep", "gpt-4o")
        self.quick = os.getenv("QUICK_LLM") or prof.get("quick", "gpt-4o-mini")
        self.timeout = float(os.getenv("LLM_TIMEOUT_S", "40"))
        self.retries = int(os.getenv("LLM_MAX_RETRIES", "2"))
        self.profile_name = prof_name or "custom"
        self._audit: list[dict] = []

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _model(self, tier: str) -> str:
        return self.deep if tier == "deep" else self.quick

    async def structured(self, tier: str, system: str, user: str, schema: Type[T]) -> T | None:
        """带 pydantic 校验的结构化输出。无 key 或失败返回 None，由上层用启发式兜底。"""
        if not self.enabled:
            return None
        model = self._model(tier)
        # 让模型直接返回 JSON
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
        headers = {"Authorization": f"Bearer {self.api_key}",
                   "Content-Type": "application/json"}
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=True) as c:
                    r = await c.post(f"{self.base_url}/chat/completions",
                                     json=payload, headers=headers)
                    r.raise_for_status()
                    js = r.json()
                content = js["choices"][0]["message"]["content"]
                obj = json.loads(content)
                validated = schema.model_validate(obj)
                self._audit.append({"model": model, "tier": tier,
                                    "usage": js.get("usage")})
                return validated
            except (json.JSONDecodeError, ValidationError, httpx.HTTPError, KeyError) as e:
                last_err = e
                await asyncio.sleep(0.4 * (attempt + 1))
        # 记录失败，返回 None 让上层用启发式
        self._audit.append({"model": model, "tier": tier, "error": str(last_err)[:120]})
        return None

    def audit(self) -> list[dict]:
        return self._audit


client = LLMClient()
