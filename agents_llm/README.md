# agents_llm/

存放"需要 LLM"的 Agent 实现。每个模块暴露一个 async 函数供 orchestrator 调用。
这里给最小骨架，真实项目请接 instructor / langchain / 自建 LLM client，
并把 system prompt 放到 agents/*.md 里以便审计。
