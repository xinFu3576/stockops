---
name: stockops-learn
version: 0.1.0
description: "一体化闭环学习:reflect(回填 realized_return) + adapt(重算权重)一次跑完。用户说 学习一次/闭环跑一遍/让团队学起来 时使用。"
metadata: { requires: { binaries: ["python3"] } }
---
# StockOps · 学习循环

**前置**: 先 Read `../stockops-shared/SKILL.md`。

## 一体化命令

```bash
python -m tools.learn --as_of 2026-07-17 --horizon 20 --min-samples 20 --apply
```

- `--apply`: 通过 min-samples 校验后写 `configs/weights.yaml`,下次决策自动生效
- `--dry-run`: 只 reflect + 显示 adapt 建议,不写

内含两步:
1. `tools.reflect`: 拿 T-20 收益,写回 MemoryRecord.realized_return / alpha
2. `tools.adapt`:  归因到 4 位分析师,给建议权重

日跑脚本 daily.sh 第 3 步已切成本 skill 的 CLI。
