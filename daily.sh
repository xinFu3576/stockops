#!/usr/bin/env bash
# StockOps v0.11.0 一键日跑：情报 → pipeline → 建议 → rebalance → 推送
# 用法: ./daily.sh [YYYY-MM-DD]  默认今天
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate
export ALL_PROXY="${ALL_PROXY:-socks5://127.0.0.1:7890}" \
       HTTPS_PROXY="${HTTPS_PROXY:-socks5://127.0.0.1:7890}" \
       HTTP_PROXY="${HTTP_PROXY:-socks5://127.0.0.1:7890}"

DATE="${1:-$(date +%F)}"
WATCH="${WATCH:-600519.SS,000858.SZ,AAPL,NVDA,0700.HK}"
EQUITY="${EQUITY:-500000}"

echo "==[stockops daily $DATE] watch=$WATCH equity=$EQUITY=="

echo "-- 0/6 news (拉取当日热点情报 + 落缓存) --"
python -m tools.investment_news --save --top 30 > /tmp/stockops_news.$$.log 2>&1 || echo "[warn] news exit non-zero"
head -8 /tmp/stockops_news.$$.log

echo "-- 1/6 batch pipeline --"
python -m tools.batch_runner --list core --date "$DATE" || echo "[warn] batch_runner exit non-zero"

echo "-- 2/6 verify --"
python -m tools.verify --tickers "$WATCH" --date "$DATE" > /tmp/stockops_verify.$$.log 2>&1 || echo "[warn] verify exit non-zero"
tail -20 /tmp/stockops_verify.$$.log

echo "-- 3/7 advise (人类可读建议 + wecom 推送 + KB 归档) --"
./manage.py advise --tickers "$WATCH" --date "$DATE" --equity "$EQUITY" \
    --output-file /tmp/stockops_advice_$DATE.md \
    --archive \
    ${NOTIFY:+--notify} || echo "[warn] advise 出错"
echo "  → /tmp/stockops_advice_$DATE.md"

echo "-- 4/7 rebalance (kelly, dry_run) --"
./manage.py rebalance --method kelly --days 5 --equity "$EQUITY" > /tmp/stockops_rebal.$$.log 2>&1 || echo "[info] rebalance 空/错误"
tail -15 /tmp/stockops_rebal.$$.log

echo "-- 5/7 reflect (T-20 学习) --"
python -m tools.learn --horizon 20 --min-samples 20 --as_of "$DATE" --apply || echo "[info] learn: 空样本或错误"

echo "-- 6/7 broker + options health --"
./manage.py broker-health --brokers dry_run,paper

echo "-- 7/7 KB 归档确认 --"
ls -lat reports/kb/*/*/*.md 2>/dev/null | head -3

if [ "${EXECUTE:-}" = "paper" ]; then
    echo "-- + (可选) 一键下单 paper --"
    ./manage.py advise --tickers "$WATCH" --date "$DATE" --equity "$EQUITY" \
        --execute paper --yes --archive || echo "[warn] execute 出错"
fi

echo "==[stockops daily] done  📄 /tmp/stockops_advice_$DATE.md · KB=reports/kb/=="
