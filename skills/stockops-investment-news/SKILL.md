---
name: stockops-investment-news
description: Use when you need to pull investment news / market rumors / macro & policy releases / company filings for the StockOps team. Aggregates 7 免登录 sources (sina 7×24 / eastmoney / yahoo / SEC EDGAR / Fed / US Treasury / xinhua),按紧迫度打分,支持关键词 + ticker 过滤,可推送到通知渠道。
---

# stockops-investment-news

## When to use

- 用户问「今天有什么大新闻/热点」「XX 公司出什么事了」「Fed 有没有讲话」
- 决策前需要事件面输入(macro/policy 触发的调仓)
- 每日 `daily.sh` 摘要报告的输入侧
- 想把突发情报推到微信/飞书/邮件

## Usage

```bash
# 1) 抓全部源 + 打紧迫度分,输出 markdown digest:
stockops investment-news

# 2) 只抓某几源:
stockops investment-news --sources cls,eastmoney,yahoo

# 3) 关键词/ticker 过滤:
stockops investment-news --keywords 央行,降息,加息
stockops investment-news --tickers 600519.SS,AAPL

# 4) 落 JSON 快照到 data/news_cache/YYYY-MM-DD.json:
stockops investment-news --save

# 5) 直接推送到微信/飞书/邮件:
stockops investment-news --top 20 --notify
```

## Under the hood

- 代码在 `tools/investment_news.py`
- 数据源(可扩展):

  | 名字 | 类型 | 内容 |
  |---|---|---|
  | `cls` | JSON | 新浪 7×24 快讯 (取代 CLS) |
  | `eastmoney` | JSONP | 东方财富 7×24 |
  | `yahoo` | RSS | Yahoo Finance 头条 |
  | `sec` | RSS | SEC EDGAR 8-K 公告 |
  | `fed` | RSS | Fed press release |
  | `treasury` | RSS | US Treasury press |
  | `xinhua` | RSS | 新华社政经 |

- 去重: URL 归一化 + title 前 40 字 hash
- 紧迫度打分 `_score_urgency`: policy/央行/公告 加权 + 时间新加权,范围 [0,1]
- 自动抽 A 股 ticker (6xxxxx.SS / 000xxx.SZ / 300xxx.SZ)

## Dashboard

打开 http://127.0.0.1:8765/news 有实时 UI: 关键词 / ticker / 源 3 维过滤,60s 自动刷新,URGENT 标红。

## Failure mode

- 单个源失败 → 静默返回空,不阻断其他源
- 全部失败 → CLI 返回 `抓取 0 条`,不 crash

## Related skills

- `stockops-alert`: 拿到 news 后触发告警报告
- `stockops-watch`: 结合价格预警交叉验证
- `stockops-shared`: 全团队共享工具约定
