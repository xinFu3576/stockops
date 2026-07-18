#!/usr/bin/env bash
# StockOps 一键日跑:pipeline(watchlist=core) + reflect + verify + 预警
# 用法: ./daily.sh [YYYY-MM-DD]  默认今天
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate
export ALL_PROXY="${ALL_PROXY:-socks5://127.0.0.1:7890}" \
       HTTPS_PROXY="${HTTPS_PROXY:-socks5://127.0.0.1:7890}" \
       HTTP_PROXY="${HTTP_PROXY:-socks5://127.0.0.1:7890}"

DATE="${1:-$(date +%F)}"
echo "==[stockops daily] $DATE=="

echo "-- 1/3 pipeline + alert --"
python -m tools.batch_runner --list core --date "$DATE" || echo "[warn] batch_runner exit non-zero"

echo "-- 2/3 verify (sanity) --"
python -m tools.verify --tickers 600519.SS,AAPL,000858.SZ --date "$DATE" > /tmp/stockops_verify.$$.log 2>&1 || echo "[warn] verify exit non-zero"
tail -30 /tmp/stockops_verify.$$.log

echo "-- 3/3 reflect (T-20 回填) --"
python -m tools.learn --horizon 20 --min-samples 20 --as_of "$DATE" --apply || echo "[info] learn: 空样本或错误"

echo "==[stockops daily] done=="
