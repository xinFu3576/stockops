---
name: stockops-reflect
version: 0.1.0
description: "回填历史决策的 realized_return + alpha,并生成 4 象限教训(对了因为/错了因为)。用户说 复盘/反思/上周结果对不对 时使用。"
metadata: { requires: { binaries: ["python3"] } }
---

# StockOps · 反思复盘

**前置**: 先 Read `../stockops-shared/SKILL.md`。

```bash
python -m tools.reflect --horizon 20 --as_of 2026-07-17
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--horizon` | 20 | 持有天数(用于计算 realized_return) |
| `--as_of` | 今天 | 反思截止日 |

写入 `data/memory/reflect_*.json`,后续 pipeline 会读取该记忆。
