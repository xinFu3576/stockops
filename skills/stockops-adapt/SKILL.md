---
name: stockops-adapt
version: 0.1.0
description: "闭环学习:根据已回填的 realized_return + alpha,给出并可选写入分析师权重 configs/weights.yaml。用户说 学习/自适应/根据表现调权重/闭环 时使用。"
metadata: { requires: { binaries: ["python3"] } }
---
# StockOps · 权重自适应

**前置**: 先 Read `../stockops-shared/SKILL.md` 并激活 venv;先跑一次 `stockops-reflect` 让 realized_return 有值。

```bash
# 只看建议
python -m tools.adapt --as_of 2026-07-17 --min-samples 20
# 写入 configs/weights.yaml,下次决策自动生效
python -m tools.adapt --as_of 2026-07-17 --min-samples 20 --apply
```

- `min-samples`: 完成回填的样本数需 ≥ 该阈值才会给出非默认建议
- `configs/weights.yaml` 会被 research_manager 在启动时读一次
