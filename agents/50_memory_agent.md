# MemoryAgent (D8)

**类型**: 工具型
**输入 / 输出**: MemoryRecord

## 存储
- 每条 Decision 落盘 \`memory/decisions/<ticker>/<YYYY-MM-DD>.json\`。
- 索引表 \`memory/index.sqlite\`：ticker, decision_ts, direction, score, realized_return。

## 查询接口
\`\`\`python
def query(ticker: str, k: int = 3) -> list[MemoryRecord]: ...
def cross_ticker_lessons(k: int = 5) -> list[str]: ...
def write(record: MemoryRecord) -> None: ...
def backfill_returns(as_of: date) -> int: ...
\`\`\`

## 与 ReflectionAgent 的分工
- MemoryAgent 只做存取，不解释。
- ReflectionAgent 才用 LLM 分析。
