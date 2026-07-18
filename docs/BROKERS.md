# 经纪商适配（Broker Adapters）

StockOps 支持 4 种下单模式：

| broker | 状态 | 依赖 | 用途 |
|---|---|---|---|
| `dry_run` | 默认 | 无 | 只走信号,不下单 |
| `paper` | 本地虚拟 | 无 | 本地撮合,持久化到 `data/paper/` |
| `ibkr` | 真实/paper | `ib_insync` + IB Gateway | 美股 IBKR 账户 |
| `futu` | 真实/simulate | `futu-api` + futu-opend | A/HK/US 富途账户 |

## 安装真实 SDK（可选）

```bash
pip install -r requirements-broker.txt
# 或单独:
pip install ib_insync futu-api
```

## IBKR 接线

1. 启动 IB Gateway（paper account）
2. `Configure → API → Enable ActiveX and Socket Clients` 打开
3. 端口默认 `4002 (paper) / 7497 (TWS paper)`
4. 环境变量:
   ```bash
   export IBKR_HOST=127.0.0.1
   export IBKR_PORT=4002
   export IBKR_CLIENT_ID=42
   ```
5. 验证：
   ```bash
   ./manage.py broker-health --brokers ibkr
   # ok=true 才能真下单
   ```
6. 真下单（需显式 flag）：
   ```bash
   ./manage.py decide AAPL --mode ibkr --i-accept-real-money
   ```

## 富途接线

1. 桌面装 futu-opend，登录账户
2. 默认端口 `11111`
3. 环境变量:
   ```bash
   export FUTU_HOST=127.0.0.1
   export FUTU_PORT=11111
   export FUTU_MARKET=HK          # HK|US|CN
   export FUTU_TRD_ENV=SIMULATE   # SIMULATE(模拟盘) | REAL(真盘)
   export FUTU_PWD_UNLOCK=xxx     # 真盘必填,模拟盘留空
   ```
4. 验证：
   ```bash
   ./manage.py broker-health --brokers futu
   ```
5. Ticker 会自动映射：`0700.HK → HK.00700`, `AAPL → US.AAPL`, `600519.SS → SH.600519`

## 安全闸

任何非 `dry_run` 模式都要显式 `--i-accept-real-money`，否则 orchestrator 直接拒绝。

## 优雅降级

- SDK 未装 → `status=stub`，不 crash
- gateway 未启动 → `status=stub`，reason 提示
- gateway 拒单 → `status=rejected`，reason 含 broker 返回

生产上跑批处理不用担心中途挂掉。
