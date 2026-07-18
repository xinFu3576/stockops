"""市场微结构因子(订单簿失衡 + 期权 IV skew)。

思路:
- OFI (Order Flow Imbalance): 从日/分钟成交推断买卖压力 (best-effort,不需 L2)
- IV Skew: 25-delta put IV - 25-delta call IV,尾部风险溢价
- Amihud illiquidity: |return| / dollar_volume (低流动 → 冲击成本高)

真实 L2 订单簿需要 quantconnect / polygon / futu L2 权限;
本模块用**日频代理指标**,与其他因子共存,不阻断主线。
"""
from __future__ import annotations
import math
from typing import Optional
from datetime import date, timedelta
from core.schemas import MarketData


def order_flow_imbalance(md: MarketData, window: int = 5) -> float:
    """近 window 日 OFI 代理:
    每日 tick_rule = sign(close - open), 权重按 volume 加权,归一化到 [-1,1]。
    正=买单主动,负=卖单主动。
    """
    bars = md.bars[-window:] if len(md.bars) >= window else md.bars
    if len(bars) < 2: return 0.0
    up_vol, dn_vol = 0.0, 0.0
    for b in bars:
        if b.close > b.open: up_vol += b.volume
        elif b.close < b.open: dn_vol += b.volume
    tot = up_vol + dn_vol
    return (up_vol - dn_vol) / tot if tot > 0 else 0.0


def amihud_illiquidity(md: MarketData, window: int = 20) -> float:
    """Amihud (2002): mean(|R_t| / dollar_volume_t)。数值越大 = 越不流动 = 冲击成本越高。
    输出规范化: log1p 后 tanh 到 [0,1]。
    """
    bars = md.bars[-window-1:] if len(md.bars) >= window+1 else md.bars
    if len(bars) < 3: return 0.0
    ratios = []
    for i in range(1, len(bars)):
        p0, p1 = bars[i-1].close, bars[i].close
        vol = bars[i].volume * p1
        if p0 <= 0 or vol <= 0: continue
        ratios.append(abs(p1 - p0) / p0 / vol * 1e6)
    if not ratios: return 0.0
    m = sum(ratios) / len(ratios)
    return math.tanh(math.log1p(m))


def realized_volatility_5d_vs_20d(md: MarketData) -> float:
    """短期 vol / 长期 vol - 1: 正=波动扩张(常见突破/恐慌),负=收敛。"""
    def rv(n):
        b = md.bars[-n-1:]
        if len(b) < 3: return 0.0
        rets = [math.log(b[i].close / b[i-1].close) for i in range(1, len(b))
                if b[i-1].close > 0 and b[i].close > 0]
        if not rets: return 0.0
        m = sum(rets) / len(rets)
        var = sum((r-m)**2 for r in rets) / max(1, len(rets)-1)
        return math.sqrt(var * 252)
    a, b = rv(5), rv(20)
    return (a / b - 1) if b > 0 else 0.0


def volume_profile_skew(md: MarketData, window: int = 20) -> float:
    """volume 分布偏度: 若近期大部分 volume 集中在下跌日 → 负; 集中在上涨日 → 正。
    简化: (sum_up_vol - sum_dn_vol) / total.
    """
    bars = md.bars[-window:]
    if not bars: return 0.0
    u, d = 0.0, 0.0
    for b in bars:
        if b.close >= b.open: u += b.volume
        else: d += b.volume
    tot = u + d
    return (u - d) / tot if tot > 0 else 0.0


def iv_skew_proxy(md: MarketData) -> Optional[float]:
    """真 IV skew 需要 options chain 数据(polygon/tradier/futu-opt),
    在没有该数据源时用 realized-vol 尾部代理:
      过去 60 日 downside_vol / upside_vol - 1
      正 = 下行波动更大 = 类 put-call skew
    """
    bars = md.bars[-60:]
    if len(bars) < 20: return None
    up_sq, dn_sq = [], []
    for i in range(1, len(bars)):
        r = (bars[i].close - bars[i-1].close) / bars[i-1].close if bars[i-1].close > 0 else 0
        if r > 0: up_sq.append(r*r)
        else: dn_sq.append(r*r)
    if not up_sq or not dn_sq: return None
    up_vol = math.sqrt(sum(up_sq)/len(up_sq))
    dn_vol = math.sqrt(sum(dn_sq)/len(dn_sq))
    return (dn_vol / up_vol - 1) if up_vol > 0 else 0.0


def compute_microstructure_bundle(md: MarketData) -> dict:
    """一次算完 6 个微结构因子,输出到 factor bundle。

    v0.9.0：iv_skew 优先用真 options chain，无 key 则退到 realized-vol 代理。
    """
    out = {
        "ofi_5d": order_flow_imbalance(md, 5),
        "ofi_20d": order_flow_imbalance(md, 20),
        "amihud_illiquidity": amihud_illiquidity(md),
        "rv_expansion": realized_volatility_5d_vs_20d(md),
        "volume_skew": volume_profile_skew(md),
    }
    # 真 IV skew 三级降级
    try:
        from tools.options_chain import fetch_options_skew
        os_r = fetch_options_skew(md.ticker)
        if os_r and os_r.iv_skew is not None:
            out["iv_skew"] = os_r.iv_skew
            out["iv_skew_source"] = os_r.source
            out["put_call_ratio"] = os_r.put_call_ratio
        else:
            out["iv_skew"] = iv_skew_proxy(md)
            out["iv_skew_source"] = "proxy"
    except Exception:
        out["iv_skew"] = iv_skew_proxy(md)
        out["iv_skew_source"] = "proxy"
    out["iv_skew_proxy"] = iv_skew_proxy(md)  # 兼容
    return out


if __name__ == "__main__":
    import asyncio, json
    from tools.market_data import fetch_market_data
    async def demo():
        for tk in ("AAPL", "600519.SS", "0700.HK"):
            try:
                md = await fetch_market_data(tk, date.today())
                out = compute_microstructure_bundle(md)
                print(f"{tk}: {json.dumps(out, ensure_ascii=False, default=lambda x: round(x,4) if isinstance(x,float) else x)}")
            except Exception as e:
                print(f"{tk}: FAIL {type(e).__name__}: {e}")
    asyncio.run(demo())
