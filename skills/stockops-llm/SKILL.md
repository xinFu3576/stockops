---
name: stockops-llm
version: 0.1.0
description: "切换 StockOps 团队使用的 LLM 后端(openai/deepseek/kimi/qwen/ark/vllm)。用户说 换模型/用豆包/用 DeepSeek/用本地 vLLM 时使用。"
metadata: { requires: { binaries: ["python3"] } }
---
# StockOps · LLM 后端切换

**前置**: 先 Read `../stockops-shared/SKILL.md`。

## 支持的 profile

| profile | base_url | 深/轻模型 | 需要 env |
|---|---|---|---|
| `openai` | api.openai.com/v1 | gpt-4o / gpt-4o-mini | OPENAI_API_KEY |
| `deepseek` | api.deepseek.com/v1 | deepseek-chat / deepseek-chat | DEEPSEEK_API_KEY |
| `kimi` | api.moonshot.cn/v1 | moonshot-v1-32k / -8k | MOONSHOT_API_KEY |
| `qwen` | dashscope aliyun | qwen-max / qwen-turbo | DASHSCOPE_API_KEY |
| `ark` | ark.cn-beijing.volces.com/api/v3 | doubao-1-5-pro-32k / lite-32k | ARK_API_KEY |
| `vllm` | 本地 vLLM | 由 VLLM_MODEL 指定 | (可选)VLLM_API_KEY |

## 用法

```bash
# 火山方舟豆包
export LLM_PROFILE=ark ARK_API_KEY=sk-xxx
# 覆盖模型
export DEEP_LLM=ep-xxxxxxxx-xxxxx QUICK_LLM=ep-xxxxxxxx-yyyyy

# 或 DeepSeek
export LLM_PROFILE=deepseek DEEPSEEK_API_KEY=...

python -m core.orchestrator --tickers AAPL --date 2026-07-17 --force
```

**无 key 静默降级到启发式兜底**,不会 crash。

## 快速检查

```bash
python -c "from agents_llm.llm_client import client; print(client.profile_name, client.base_url, client.deep, 'has_key=', bool(client.api_key))"
```
