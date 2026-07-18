"""零依赖团队仪表盘:标准库 http.server 起在 http://localhost:8765/
展示 team 状态 / paper 账户 / 最近报告 / 权重 / 决策记忆。

用法:
  python -m dashboard.server              # 默认 8765
  python -m dashboard.server --port 9000
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, threading, html
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent


def _read_json(p):
    try: return json.load(open(p))
    except Exception: return None


def _team_status():
    return {
        "project": str(ROOT),
        "weights": _read_json(ROOT / "configs" / "weights.yaml") or "(默认)",
        "paper": _read_json(ROOT / "data" / "paper" / "account.json"),
        "memory": _memory_count(),
        "reports": _list_reports(),
        "watchlist_state": _list_batch_state(),
    }


def _memory_count():
    d = ROOT / "data" / "memory"
    if not d.exists(): return 0
    return sum(len(os.listdir(d / t)) for t in os.listdir(d) if (d / t).is_dir())


def _list_reports():
    d = ROOT / "reports"
    if not d.exists(): return []
    files = sorted(d.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]
    return [{"name": f.name, "mtime": f.stat().st_mtime, "size": f.stat().st_size} for f in files]


def _list_batch_state():
    d = ROOT / "data" / "batch_state"
    if not d.exists(): return []
    return sorted([p.name for p in d.glob("*.json")])[-5:]


HTML = """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>StockOps · 团队仪表盘</title>
<style>
  body{font-family:-apple-system,SF Pro,Segoe UI,sans-serif;margin:0;background:#0e1116;color:#e6e6e6;padding:24px}
  h1{margin:0 0 20px 0;font-size:22px}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
  .card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}
  .card h3{margin:0 0 12px 0;color:#58a6ff;font-size:14px;letter-spacing:1px;text-transform:uppercase}
  pre{background:#0d1117;padding:12px;border-radius:6px;overflow-x:auto;font-size:12px;margin:0}
  .kv{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px dashed #30363d}
  .kv:last-child{border:0}
  .kv b{color:#7ee787}
  a{color:#58a6ff}
  .green{color:#7ee787}.red{color:#ff7b72}.yellow{color:#f0883e}
  .actions button{background:#238636;color:#fff;border:0;padding:8px 12px;border-radius:5px;cursor:pointer;margin-right:8px}
  .actions button.danger{background:#c93c37}
  .actions button:hover{filter:brightness(1.15)}
  input,select{background:#0d1117;color:#e6e6e6;border:1px solid #30363d;padding:6px 8px;border-radius:4px}
  .log{max-height:280px;overflow-y:auto}
</style></head><body>
<h1>📈 StockOps · 团队仪表盘 <small style="color:#7d8590">v0.6.0</small></h1>
<div style="margin-bottom:16px"><input id="chartTk" placeholder="600519.SS" size="20"/><button onclick="window.open('/chart/'+encodeURIComponent(document.getElementById('chartTk').value||'AAPL'),'_blank')" style="background:#1f6feb;color:#fff;border:0;padding:6px 12px;border-radius:5px;cursor:pointer;margin-left:8px">🕯 打开 K 线</button><input id="cmpTk" placeholder="AAPL,600519.SS,0700.HK" size="30" style="margin-left:16px"/><button onclick="window.open('/compare/'+encodeURIComponent(document.getElementById('cmpTk').value||'AAPL,600519.SS'),'_blank')" style="background:#8957e5;color:#fff;border:0;padding:6px 12px;border-radius:5px;cursor:pointer;margin-left:8px">📊 网格对比</button><input id="btTk" placeholder="AAPL" size="20" style="margin-left:16px"/><button onclick="window.open('/equity/'+encodeURIComponent(document.getElementById('btTk').value||'AAPL'),'_blank')" style="background:#3fb950;color:#fff;border:0;padding:6px 12px;border-radius:5px;cursor:pointer;margin-left:8px">📈 回测曲线</button><a href="/pnl" style="margin-left:16px;color:#f0883e">💰 P&L 归因</a><a href="/news" style="margin-left:16px;color:#f0883e">🗞 情报</a><a href="/ab" style="margin-left:16px;color:#f0883e">🧪 A/B</a></div>
<div class="grid">
  <div class="card"><h3>项目状态</h3><div id="status"></div></div>
  <div class="card"><h3>因子权重</h3><pre id="weights"></pre></div>
  <div class="card"><h3>Paper 账户</h3><pre id="paper"></pre></div>
  <div class="card"><h3>批处理快照</h3><pre id="batch"></pre></div>
  <div class="card"><h3>最近报告</h3><ul id="reports" style="padding-left:16px"></ul></div>
  <div class="card"><h3>快捷操作</h3>
    <div class="actions">
      <div style="margin-bottom:10px">
        <input id="tickers" placeholder="AAPL,600519.SS" size="30" />
        <select id="mode"><option>dry_run</option><option>paper</option></select>
      </div>
      <button onclick="run('decide')">决策</button>
      <button onclick="run('backtest')">回测</button>
      <button onclick="run('verify')">健康检查</button>
      <button onclick="run('learn')">学习一次</button>
      <button class="danger" onclick="if(confirm('清空 paper 账户?'))run('paper-reset')">清 paper</button>
    </div>
    <pre id="log" class="log" style="margin-top:12px"></pre>
  </div>
</div>
<script>
async function refresh(){
  const s = await fetch('/api/status').then(r=>r.json());
  document.getElementById('status').innerHTML =
    `<div class="kv"><span>项目</span><b>${s.project}</b></div>`+
    `<div class="kv"><span>决策记忆</span><b>${s.memory}</b></div>`+
    `<div class="kv"><span>报告数</span><b>${s.reports.length}</b></div>`;
  document.getElementById('weights').textContent = JSON.stringify(s.weights,null,2);
  document.getElementById('paper').textContent = s.paper? JSON.stringify(s.paper,null,2) : '(空)';
  document.getElementById('batch').textContent = s.watchlist_state.join('\\n') || '(空)';
  document.getElementById('reports').innerHTML = s.reports.map(r=>
    `<li><a href="/report/${encodeURIComponent(r.name)}">${r.name}</a> (${(r.size/1024).toFixed(1)}KB)</li>`).join('');
}
async function run(action){
  const tk = document.getElementById('tickers').value || 'AAPL';
  const mode = document.getElementById('mode').value;
  const url = `/api/run?action=${action}&tickers=${encodeURIComponent(tk)}&mode=${mode}`;
  document.getElementById('log').textContent = '运行中...';
  const r = await fetch(url).then(r=>r.text());
  document.getElementById('log').textContent = r.slice(0,4000);
  refresh();
}
refresh(); setInterval(refresh, 15000);
</script>
</body></html>
"""



CHART_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>K 线 · __TICKER__</title>
<style>
  body{background:#0e1116;color:#e6e6e6;font-family:-apple-system,SF Pro,sans-serif;margin:0;padding:16px}
  h2{margin:0 0 12px 0;font-size:16px}
  #wrap{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px}
  canvas{background:#0d1117;display:block;border-radius:4px}
  .info{color:#7d8590;font-size:12px;margin-top:8px}
  .kv{display:inline-block;margin-right:16px}
  .kv b{color:#7ee787}
  a{color:#58a6ff}
</style></head><body>
<h2>🕯 K 线 · __TICKER__ <small><a href="/">← 返回</a></small></h2>
<div id="wrap">
  <canvas id="chart" width="1200" height="500"></canvas>
  <div class="info" id="meta">加载中...</div>
</div>
<script>
async function load(){
  const r = await fetch('/api/bars?ticker=__TICKER__&lookback=180').then(r=>r.json());
  if(r.error){document.getElementById('meta').textContent='加载失败: '+r.error;return}
  const bars = r.bars;
  const c = document.getElementById('chart'), ctx = c.getContext('2d');
  const W = c.width, H = c.height, PAD_L=60, PAD_R=10, PAD_T=20, PAD_B=40;
  const iw = W-PAD_L-PAD_R, ih = H-PAD_T-PAD_B;
  const highs = bars.map(b=>b.high), lows = bars.map(b=>b.low);
  const hi = Math.max(...highs), lo = Math.min(...lows);
  const y = v => PAD_T + ih - (v-lo)/(hi-lo)*ih;
  const bw = iw / bars.length;
  ctx.fillStyle='#0d1117'; ctx.fillRect(0,0,W,H);
  // grid
  ctx.strokeStyle='#21262d'; ctx.fillStyle='#7d8590'; ctx.font='11px monospace';
  for(let i=0;i<=5;i++){
    const yy=PAD_T+ih*i/5, v=hi-(hi-lo)*i/5;
    ctx.beginPath(); ctx.moveTo(PAD_L,yy); ctx.lineTo(W-PAD_R,yy); ctx.stroke();
    ctx.fillText(v.toFixed(2), 6, yy+4);
  }
  // MA20
  function ma(n){const out=[];for(let i=0;i<bars.length;i++){if(i<n-1){out.push(null);continue}
    let s=0;for(let j=i-n+1;j<=i;j++)s+=bars[j].close;out.push(s/n)}return out;}
  function drawLine(arr,color){ctx.strokeStyle=color;ctx.lineWidth=1.5;ctx.beginPath();
    let started=false;arr.forEach((v,i)=>{if(v==null)return;const x=PAD_L+i*bw+bw/2,yy=y(v);
    if(!started){ctx.moveTo(x,yy);started=true}else ctx.lineTo(x,yy);});ctx.stroke();}
  // candles
  bars.forEach((b,i)=>{
    const x = PAD_L + i*bw, mid = x+bw/2;
    const up = b.close>=b.open;
    ctx.strokeStyle = up?'#3fb950':'#f85149';
    ctx.fillStyle = up?'#238636':'#da3633';
    ctx.beginPath(); ctx.moveTo(mid,y(b.high)); ctx.lineTo(mid,y(b.low)); ctx.stroke();
    const oy=y(b.open), cy=y(b.close);
    const top=Math.min(oy,cy), h=Math.max(1,Math.abs(cy-oy));
    ctx.fillRect(x+bw*0.15, top, bw*0.7, h);
  });
  drawLine(ma(5), '#f0883e');
  drawLine(ma(20), '#58a6ff');
  drawLine(ma(60), '#bc8cff');
  // x-axis dates (5 ticks)
  ctx.fillStyle='#7d8590';
  for(let i=0;i<5;i++){
    const idx=Math.floor(bars.length*i/5);
    const x=PAD_L+idx*bw+bw/2;
    ctx.fillText(bars[idx].date, x-30, H-PAD_B+18);
  }
  const last=bars[bars.length-1];
  document.getElementById('meta').innerHTML =
    `<span class="kv">数据源 <b>${r.source}</b></span>`+
    `<span class="kv">K 数 <b>${bars.length}</b></span>`+
    `<span class="kv">最新 <b>${last.date}</b></span>`+
    `<span class="kv">收盘 <b>${last.close.toFixed(2)}</b></span>`+
    `<span class="kv">MA5 <span style="color:#f0883e">━</span> MA20 <span style="color:#58a6ff">━</span> MA60 <span style="color:#bc8cff">━</span></span>`;
}
load();
</script></body></html>"""


def _fetch_bars_sync(ticker: str, lookback: int = 180) -> dict:
    """同步版拉取,给 /api/bars 用。"""
    import asyncio
    from datetime import date as _d
    try:
        from tools.market_data import fetch_market_data
    except Exception as e:
        return {"error": f"import failed: {e}"}
    try:
        md = asyncio.run(fetch_market_data(ticker, _d.today(), lookback=lookback))
        bars = [{"date": b.date.isoformat(), "open": b.open, "high": b.high,
                 "low": b.low, "close": b.close, "volume": b.volume}
                for b in md.bars[-lookback:]]
        return {"ticker": ticker, "source": md.source, "bars": bars}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}



COMPARE_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>网格对比</title>
<style>
  body{background:#0e1116;color:#e6e6e6;font-family:-apple-system,SF Pro,sans-serif;margin:0;padding:16px}
  h2{margin:0 0 12px 0;font-size:16px}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(500px,1fr));gap:12px}
  .card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:8px}
  canvas{background:#0d1117;display:block;border-radius:4px;width:100%;height:280px}
  .meta{color:#7d8590;font-size:12px;padding:6px 4px 2px}
  .meta b{color:#7ee787}
  a{color:#58a6ff}
</style></head><body>
<h2>📊 网格对比 <small><a href="/">← 返回</a></small></h2>
<div class="grid" id="grid"></div>
<script>
const TICKERS = __TICKERS__;
async function draw(tk, canvas, meta){
  const r = await fetch(`/api/bars?ticker=${encodeURIComponent(tk)}&lookback=120`).then(r=>r.json());
  if(r.error){meta.textContent = tk+': '+r.error;return}
  const bars = r.bars;
  const c = canvas, ctx = c.getContext('2d');
  c.width = c.clientWidth; c.height = c.clientHeight;
  const W=c.width,H=c.height,P=30;
  const highs = bars.map(b=>b.high), lows = bars.map(b=>b.low);
  const hi = Math.max(...highs), lo = Math.min(...lows);
  const y = v => P + (H-2*P) - (v-lo)/(hi-lo)*(H-2*P);
  const bw = (W-2*P)/bars.length;
  ctx.fillStyle='#0d1117'; ctx.fillRect(0,0,W,H);
  ctx.strokeStyle='#21262d';
  for(let i=0;i<=4;i++){const yy=P+(H-2*P)*i/4;ctx.beginPath();ctx.moveTo(P,yy);ctx.lineTo(W-P,yy);ctx.stroke();}
  bars.forEach((b,i)=>{
    const x = P + i*bw, mid = x+bw/2;
    const up = b.close>=b.open;
    ctx.strokeStyle = up?'#3fb950':'#f85149';
    ctx.fillStyle = up?'#238636':'#da3633';
    ctx.beginPath(); ctx.moveTo(mid,y(b.high)); ctx.lineTo(mid,y(b.low)); ctx.stroke();
    const oy=y(b.open),cy=y(b.close),top=Math.min(oy,cy),h=Math.max(1,Math.abs(cy-oy));
    ctx.fillRect(x+bw*0.15,top,bw*0.7,h);
  });
  const first=bars[0].close, last=bars[bars.length-1].close;
  const chg = ((last-first)/first*100).toFixed(2);
  const col = chg>=0?'#3fb950':'#f85149';
  meta.innerHTML = `<b>${tk}</b> <span style='color:${col}'>${chg}%</span> · ${bars.length}bars · ${r.source} · 最新 ${last.toFixed(2)}`;
}
const g = document.getElementById('grid');
TICKERS.forEach(tk=>{
  const card = document.createElement('div'); card.className='card';
  const meta = document.createElement('div'); meta.className='meta'; meta.textContent = tk+' 加载中';
  const cv = document.createElement('canvas');
  card.appendChild(meta); card.appendChild(cv); g.appendChild(card);
  setTimeout(()=>draw(tk,cv,meta), 50);
});
</script></body></html>"""

EQUITY_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>回测曲线 · __TICKER__</title>
<style>
  body{background:#0e1116;color:#e6e6e6;font-family:-apple-system,SF Pro,sans-serif;margin:0;padding:16px}
  h2{margin:0 0 12px 0;font-size:16px}
  .row{display:flex;gap:16px;flex-wrap:wrap}
  .card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}
  canvas{background:#0d1117;border-radius:4px;display:block}
  .metrics{font-size:13px;line-height:1.8}
  .metrics .kv{display:flex;justify-content:space-between;min-width:220px;border-bottom:1px dashed #30363d;padding:4px 0}
  .metrics b{color:#7ee787}
  a{color:#58a6ff}
</style></head><body>
<h2>📈 回测曲线 · __TICKER__ <small><a href="/">← 返回</a></small></h2>
<div class="row">
  <div class="card"><canvas id="eq" width="900" height="420"></canvas></div>
  <div class="card metrics" id="mx">加载中...</div>
</div>
<script>
async function load(){
  const r = await fetch('/api/equity?ticker=__TICKER__&lookback=500').then(r=>r.json());
  if(r.error){document.getElementById('mx').textContent = 'ERROR: '+r.error;return}
  const eq = r.equity, dates = r.dates, bench_ann = r.benchmark_ann;
  const c = document.getElementById('eq'), ctx = c.getContext('2d');
  const W=c.width,H=c.height,P=50;
  ctx.fillStyle='#0d1117'; ctx.fillRect(0,0,W,H);
  const hi=Math.max(...eq), lo=Math.min(...eq);
  const y = v => P + (H-2*P) - (v-lo)/(hi-lo)*(H-2*P);
  ctx.strokeStyle='#21262d'; ctx.fillStyle='#7d8590'; ctx.font='11px monospace';
  for(let i=0;i<=5;i++){
    const yy=P+(H-2*P)*i/5, v=hi-(hi-lo)*i/5;
    ctx.beginPath(); ctx.moveTo(P,yy); ctx.lineTo(W-P,yy); ctx.stroke();
    ctx.fillText(v.toFixed(3), 4, yy+4);
  }
  ctx.strokeStyle='#58a6ff'; ctx.lineWidth=2; ctx.beginPath();
  eq.forEach((v,i)=>{const x=P+(W-2*P)*i/(eq.length-1); i? ctx.lineTo(x,y(v)) : ctx.moveTo(x,y(v));});
  ctx.stroke();
  ctx.strokeStyle='#f0883e'; ctx.setLineDash([4,4]); ctx.beginPath();
  ctx.moveTo(P,y(1)); ctx.lineTo(W-P,y(1)); ctx.stroke(); ctx.setLineDash([]);
  ctx.fillStyle='#7d8590';
  ctx.fillText(dates[0], P, H-P+16);
  ctx.fillText(dates[dates.length-1], W-P-70, H-P+16);
  document.getElementById('mx').innerHTML = `
    <div class="kv"><span>数据源</span><b>${r.source}</b></div>
    <div class="kv"><span>期间</span><b>${dates[0]} → ${dates[dates.length-1]}</b></div>
    <div class="kv"><span>年化</span><b>${(r.annual_return*100).toFixed(2)}%</b></div>
    <div class="kv"><span>基准年化</span><b>${(bench_ann*100).toFixed(2)}%</b></div>
    <div class="kv"><span>α vs 基准</span><b>${(r.alpha_vs_benchmark*100).toFixed(2)}%</b></div>
    <div class="kv"><span>Sharpe</span><b>${r.sharpe.toFixed(2)}</b></div>
    <div class="kv"><span>最大回撤</span><b>${(r.max_drawdown*100).toFixed(2)}%</b></div>
    <div class="kv"><span>胜率</span><b>${(r.win_rate*100).toFixed(1)}%</b></div>
    <div class="kv"><span>交易次数</span><b>${r.trades}</b></div>
    <div class="kv"><span>换手 (总)</span><b>${r.turnover.toFixed(1)}</b></div>
    <div class="kv"><span>成本拖累</span><b>${(r.attribution.cost_drag*100).toFixed(2)}%</b></div>
  `;
}
load();
</script></body></html>"""

PNL_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>P&L 归因</title>
<style>
  body{background:#0e1116;color:#e6e6e6;font-family:-apple-system,SF Pro,sans-serif;margin:0;padding:16px}
  h2{margin:0 0 12px 0;font-size:16px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  .card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}
  h3{margin:0 0 12px 0;color:#58a6ff;font-size:13px}
  table{width:100%;border-collapse:collapse;font-size:12px}
  th,td{padding:6px 8px;text-align:right;border-bottom:1px solid #21262d}
  th{color:#7d8590;font-weight:normal;text-align:left}
  td.tk{text-align:left;color:#58a6ff}
  .pos{color:#3fb950}.neg{color:#f85149}
  a{color:#58a6ff}
</style></head><body>
<h2>💰 实时 P&L + Agent 归因 <small><a href="/">← 返回</a></small></h2>
<div id="body">加载中...</div>
<script>
function fmt(v){return (v*100).toFixed(2)+'%'}
function money(v){return '$'+v.toFixed(2)}
async function load(){
  const r = await fetch('/api/pnl').then(r=>r.json());
  const b = document.getElementById('body');
  if(r.error){b.textContent = 'ERROR: '+r.error;return}
  let posHtml = `<table><tr><th>Ticker</th><th>Qty</th><th>Cost</th><th>Now</th><th>PnL</th><th>Ret</th></tr>`;
  r.positions.forEach(p=>{
    const cls = p.pnl>=0 ? 'pos' : 'neg';
    posHtml += `<tr><td class='tk'>${p.ticker}</td><td>${p.qty}</td><td>${money(p.cost)}</td><td>${money(p.mkt)}</td><td class='${cls}'>${money(p.pnl)}</td><td class='${cls}'>${fmt(p.ret)}</td></tr>`;
  });
  posHtml += '</table>';
  let agentHtml = `<table><tr><th>Agent</th><th>贡献 pnl</th><th>决策数</th><th>命中率</th><th>平均 α</th></tr>`;
  r.agents.forEach(a=>{
    const cls = a.pnl>=0 ? 'pos' : 'neg';
    agentHtml += `<tr><td class='tk'>${a.name}</td><td class='${cls}'>${money(a.pnl)}</td><td>${a.n}</td><td>${fmt(a.hit)}</td><td class='${cls}'>${fmt(a.avg_alpha)}</td></tr>`;
  });
  agentHtml += '</table>';
  b.innerHTML = `
    <div class="card" style="margin-bottom:16px">
      <h3>汇总</h3>
      <table><tr>
        <td>现金 <b>${money(r.cash)}</b></td>
        <td>持仓市值 <b>${money(r.total_mkt)}</b></td>
        <td>总账户 <b>${money(r.total_equity)}</b></td>
        <td>浮动 P&L <b class="${r.total_pnl>=0?'pos':'neg'}">${money(r.total_pnl)} (${fmt(r.total_ret)})</b></td>
        <td>决策数 <b>${r.total_decisions}</b></td>
      </tr></table>
    </div>
    <div class="grid">
      <div class="card"><h3>持仓 P&L (paper)</h3>${posHtml}</div>
      <div class="card"><h3>Agent 归因 (T+20 realized)</h3>${agentHtml}</div>
    </div>`;
}
load();
</script></body></html>"""

def _fetch_equity_sync(ticker: str, lookback: int = 500) -> dict:
    import asyncio
    from datetime import date as _d
    try:
        from tools.market_data import fetch_market_data
        from tools.backtest import backtest_series
    except Exception as e:
        return {"error": f"import: {e}"}
    try:
        md = asyncio.run(fetch_market_data(ticker, _d.today(), lookback=lookback))
        res = backtest_series(md)
        return {
            "ticker": ticker, "source": md.source,
            "equity": res["equity_curve"], "dates": res["dates"],
            "annual_return": res["annual_return"],
            "benchmark_ann": res["benchmark_ann"],
            "alpha_vs_benchmark": res["alpha_vs_benchmark"],
            "sharpe": res["sharpe"], "max_drawdown": res["max_drawdown"],
            "win_rate": res["win_rate"], "trades": res["trades"],
            "turnover": res["turnover"],
            "attribution": res["attribution"],
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _pnl_sync() -> dict:
    """当前 paper 账户 + agent 归因(读 realized memory)。"""
    import asyncio, json, os
    from pathlib import Path
    from datetime import date as _d
    from tools.brokers import get_broker
    try:
        from tools.market_data import fetch_market_data
    except Exception:
        fetch_market_data = None
    try:
        b = get_broker("paper")
        pos = asyncio.run(b.positions())
        cash = asyncio.run(b.cash())
    except Exception as e:
        return {"error": f"broker: {e}"}
    total_mkt = 0.0; total_cost = 0.0; positions = []
    for tk, info in pos.items():
        qty = info.get("qty", 0); cost_p = info.get("cost", 0.0)
        cost_val = qty * cost_p
        # Get last price (best effort)
        last = cost_p
        if fetch_market_data:
            try:
                md = asyncio.run(fetch_market_data(tk, _d.today(), lookback=30))
                last = md.bars[-1].close
            except Exception: pass
        mkt = qty * last
        pnl = mkt - cost_val
        ret = pnl / cost_val if cost_val else 0.0
        positions.append({"ticker": tk, "qty": qty, "cost": cost_p, "mkt": last, "pnl": pnl, "ret": ret})
        total_mkt += mkt; total_cost += cost_val

    # Agent 归因: 遍历 data/memory/*/*.json 中 realized_return_20d
    ROOT = Path(__file__).resolve().parent.parent
    memroot = ROOT / "data" / "memory"
    agent_stats = {}  # name -> [ret_list]
    total_decisions = 0
    if memroot.exists():
        for f in memroot.rglob("*.json"):
            try:
                rec = json.load(open(f))
                total_decisions += 1
                dec = rec.get("decision") or {}
                realized = rec.get("realized_return_20d")
                if realized is None: continue
                verdicts = dec.get("analyst_verdicts") or []
                dir_str = (dec.get("direction") or "hold").lower()
                sign = 1 if dir_str == "buy" else (-1 if dir_str == "sell" else 0)
                alpha = realized * sign  # 简化: 方向 * 实际收益
                for v in verdicts:
                    role = v.get("role") or "unknown"
                    agent_stats.setdefault(role, []).append(alpha)
            except Exception: continue
    agents = []
    for name, rets in agent_stats.items():
        n = len(rets); hit = sum(1 for r in rets if r>0)/n if n else 0
        avg = sum(rets)/n if n else 0
        pnl = sum(rets) * 1000  # 假设名义 pnl scale
        agents.append({"name": name, "pnl": pnl, "n": n, "hit": hit, "avg_alpha": avg})
    agents.sort(key=lambda a: -a["pnl"])
    if not agents:
        agents = [{"name": "(尚无 realized 数据,跑 stockops learn 先)", "pnl": 0, "n": 0, "hit": 0, "avg_alpha": 0}]

    total_pnl = total_mkt - total_cost
    total_equity = cash + total_mkt
    total_ret = total_pnl / total_cost if total_cost else 0
    return {
        "cash": cash, "total_mkt": total_mkt, "total_equity": total_equity,
        "total_pnl": total_pnl, "total_ret": total_ret,
        "total_decisions": total_decisions,
        "positions": positions, "agents": agents,
    }



NEWS_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>投资情报</title>
<style>
  body{background:#0e1116;color:#e6e6e6;font-family:-apple-system,SF Pro,sans-serif;margin:0;padding:16px}
  h2{margin:0 0 12px 0;font-size:16px}
  .bar{margin-bottom:12px}
  .bar input,.bar select{background:#0d1117;color:#e6e6e6;border:1px solid #30363d;padding:6px 8px;border-radius:4px;margin-right:8px}
  .bar button{background:#238636;color:#fff;border:0;padding:6px 12px;border-radius:5px;cursor:pointer}
  .item{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:10px 14px;margin-bottom:8px}
  .item .title{font-size:13px;line-height:1.5}
  .item a{color:#58a6ff;text-decoration:none}
  .item .meta{font-size:11px;color:#7d8590;margin-top:4px}
  .tag{display:inline-block;background:#21262d;color:#7ee787;padding:1px 6px;border-radius:3px;font-size:10px;margin-right:6px}
  .urg{background:#c93c37;color:#fff}
  .tk{background:#1f6feb;color:#fff}
  #stats{color:#7d8590;font-size:12px;margin-bottom:12px}
</style></head><body>
<h2>🗞 投资情报聚合 <small><a href="/">← 返回</a></small></h2>
<div class="bar">
  <input id="kw" placeholder="关键词过滤 (逗号分隔)" size="30"/>
  <input id="tk" placeholder="ticker (AAPL,600519.SS)" size="25"/>
  <select id="src">
    <option value="">全部源</option>
    <option>sina_7x24</option><option>eastmoney_724</option>
    <option>yahoo_finance</option><option>sec_edgar</option>
    <option>fed</option><option>us_treasury</option><option>xinhua</option>
  </select>
  <select id="top"><option>50</option><option>100</option><option>200</option></select>
  <button onclick="load()">🔄 刷新</button>
</div>
<div id="stats">加载中...</div>
<div id="list"></div>
<script>
async function load(){
  const kw = document.getElementById('kw').value;
  const tk = document.getElementById('tk').value;
  const src = document.getElementById('src').value;
  const top = document.getElementById('top').value;
  const params = new URLSearchParams({top, ...(kw?{kw}:{}), ...(tk?{tk}:{}), ...(src?{src}:{})});
  const r = await fetch('/api/news?' + params).then(r=>r.json());
  if(r.error){document.getElementById('stats').textContent='ERROR: '+r.error;return}
  document.getElementById('stats').innerHTML =
    `${r.count} 条 · 抓取源分布: ` +
    Object.entries(r.by_source||{}).map(([k,v])=>`<span class='tag'>${k} ${v}</span>`).join('');
  const list = document.getElementById('list');
  list.innerHTML = r.items.map(it => {
    const tks = (it.tickers||[]).slice(0,5).map(t=>`<span class='tag tk'>${t}</span>`).join('');
    const tags = (it.tags||[]).map(t=>`<span class='tag'>${t}</span>`).join('');
    const urg = it.urgency>=0.75 ? `<span class='tag urg'>URGENT ${(it.urgency*100).toFixed(0)}%</span>` : '';
    const ts = it.ts ? new Date(it.ts).toLocaleString('zh-CN',{hour12:false}) : '';
    return `<div class="item">
      <div class="title">${urg}${tks}<a href="${it.url}" target="_blank">${escape(it.title)}</a></div>
      <div class="meta">[${it.source}] · ${ts} ${tags}</div>
    </div>`;
  }).join('');
}
function escape(s){return String(s||'').replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))}
load();
setInterval(load, 60000);
</script></body></html>"""


def _news_sync(params: dict) -> dict:
    """dashboard 端点:重跑抓取(或读 cache)+ 过滤 + 打分。"""
    import asyncio
    from tools.investment_news import fetch_all, keyword_filter, ticker_filter, _score_urgency, load_latest
    try:
        sources = params.get("src", [None])[0]
        sources = [sources] if sources else None
        # 优先用 60s 内的 cache,否则重跑
        cache = load_latest()
        use_cache = False
        if cache:
            try:
                from datetime import datetime as _dt
                # cache 是 today 的话直接用
                if cache.get("as_of") == _dt.today().date().isoformat():
                    use_cache = True
            except Exception: pass
        if use_cache and not sources:
            items = cache.get("items", [])
        else:
            items = asyncio.run(fetch_all(sources))
        kw = params.get("kw", [None])[0]
        if kw:
            items = keyword_filter(items, kw.split(","))
        tk = params.get("tk", [None])[0]
        if tk:
            items = ticker_filter(items, tk.split(","))
        top = int(params.get("top", ["100"])[0])
        for it in items:
            it["urgency"] = _score_urgency(it)
        items.sort(key=lambda x: -x.get("urgency", 0))
        items = items[:top]
        by_source: dict = {}
        for it in items:
            s = it.get("source","?")
            by_source[s] = by_source.get(s, 0) + 1
        return {"count": len(items), "items": items, "by_source": by_source}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}



class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return self._send(200, HTML)
        if u.path == "/api/status":
            return self._send(200, json.dumps(_team_status(), default=str),
                              "application/json; charset=utf-8")
        if u.path.startswith("/report/"):
            fname = u.path[len("/report/"):]
            fp = ROOT / "reports" / fname
            if not fp.exists() or ".." in fname:
                return self._send(404, "not found", "text/plain")
            body = f"<pre style='background:#0d1117;color:#e6e6e6;padding:24px;font-family:monospace;font-size:12px'>{html.escape(open(fp).read())}</pre>"
            return self._send(200, body)
        if u.path == "/api/run":
            q = parse_qs(u.query)
            action = q.get("action", ["decide"])[0]
            tickers = q.get("tickers", ["AAPL"])[0]
            mode = q.get("mode", ["dry_run"])[0]
            py = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv").exists() else sys.executable
            today = date.today().isoformat()
            cmd_map = {
                "decide": [py, "-m", "core.orchestrator", "--tickers", tickers,
                           "--date", today, "--mode", mode, "--force",
                           *(["--i-accept-real-money"] if mode != "dry_run" else [])],
                "backtest": [py, "-m", "tools.backtest_cli", "--tickers", tickers,
                             "--date", today, "--lookback", "250"],
                "verify": [py, "-m", "tools.verify", "--tickers", tickers, "--date", today],
                "learn": [py, "-m", "tools.learn", "--as_of", today],
                "paper-reset": [py, str(ROOT / "manage.py"), "paper-reset"],
            }
            cmd = cmd_map.get(action)
            if not cmd:
                return self._send(400, f"unknown action: {action}", "text/plain")
            try:
                p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=120)
                out = (p.stdout or "") + (p.stderr or "")
                return self._send(200, out, "text/plain; charset=utf-8")
            except subprocess.TimeoutExpired:
                return self._send(504, "timeout", "text/plain")
        if u.path.startswith("/chart/"):
            tk = u.path[len("/chart/"):] or "AAPL"
            import urllib.parse as _up
            tk = _up.unquote(tk)
            return self._send(200, CHART_HTML.replace("__TICKER__", html.escape(tk)))
        if u.path == "/api/bars":
            q = parse_qs(u.query)
            tk = q.get("ticker", ["AAPL"])[0]
            lb = int(q.get("lookback", ["180"])[0])
            data = _fetch_bars_sync(tk, lb)
            return self._send(200, json.dumps(data, default=str),
                              "application/json; charset=utf-8")
        if u.path.startswith("/compare/"):
            import urllib.parse as _up
            raw = _up.unquote(u.path[len("/compare/"):])
            tks = [t.strip() for t in raw.split(",") if t.strip()]
            import json as _j
            body = COMPARE_HTML.replace("__TICKERS__", _j.dumps(tks))
            return self._send(200, body)
        if u.path.startswith("/equity/"):
            import urllib.parse as _up
            tk = _up.unquote(u.path[len("/equity/"):]) or "AAPL"
            return self._send(200, EQUITY_HTML.replace("__TICKER__", html.escape(tk)))
        if u.path == "/pnl":
            return self._send(200, PNL_HTML)
        if u.path == "/api/equity":
            q = parse_qs(u.query)
            tk = q.get("ticker", ["AAPL"])[0]
            lb = int(q.get("lookback", ["500"])[0])
            data = _fetch_equity_sync(tk, lb)
            return self._send(200, json.dumps(data, default=str),
                              "application/json; charset=utf-8")
        if u.path == "/api/pnl":
            data = _pnl_sync()
            return self._send(200, json.dumps(data, default=str),
                              "application/json; charset=utf-8")
        if u.path == "/news":
            return self._send(200, NEWS_HTML)
        if u.path == "/api/news":
            data = _news_sync(parse_qs(u.query))
            return self._send(200, json.dumps(data, default=str, ensure_ascii=False).encode("utf-8"),
                              "application/json; charset=utf-8")
        if u.path == "/ab":
            return self._send(200, AB_HTML)
        if u.path == "/api/ab":
            data = _ab_sync(parse_qs(u.query))
            return self._send(200, json.dumps(data, default=str, ensure_ascii=False).encode("utf-8"),
                              "application/json; charset=utf-8")
        if u.path == "/advise":
            return self._send(200, ADVISE_HTML)
        if u.path == "/api/notify":
            data = _notify_sync(parse_qs(u.query))
            return self._send(200, json.dumps(data, default=str, ensure_ascii=False).encode("utf-8"),
                              "application/json; charset=utf-8")
        if u.path == "/api/advise":
            data = _advise_sync(parse_qs(u.query))
            return self._send(200, json.dumps(data, default=str, ensure_ascii=False).encode("utf-8"),
                              "application/json; charset=utf-8")
        return self._send(404, "not found", "text/plain")

# ============== A/B 实验对比（v0.9.0） ==============
def _ab_sync(params: dict) -> dict:
    """跑两组权重的历史决策对比：读 memory 里所有 decisions，用 A、B 两组权重重放，比较累计收益/胜率。"""
    from tools.adapt import load_weights, DEFAULT_WEIGHTS, ANALYSTS
    from tools.memory import iter_records
    from core.schemas import Direction
    from datetime import date, timedelta

    a_raw = params.get("a", [None])[0] or ""
    b_raw = params.get("b", [None])[0] or ""
    days = int((params.get("days", ["60"])[0]) or "60")

    def _parse(s: str, default: dict) -> dict:
        try:
            if not s: return default
            parts = dict(kv.split(":") for kv in s.split(","))
            return {k: float(parts.get(k, default[k])) for k in ANALYSTS}
        except Exception:
            return default

    wA = _parse(a_raw, load_weights())
    wB = _parse(b_raw, DEFAULT_WEIGHTS)

    _DIR = {Direction.STRONG_BUY: 1.0, Direction.BUY: 0.5, Direction.HOLD: 0.0,
            Direction.SELL: -0.5, Direction.STRONG_SELL: -1.0}

    since = date.today() - timedelta(days=days)
    recs = []
    try:
        for r in iter_records():
            if r.get("decision", {}).get("as_of"):
                d = r["decision"]["as_of"]
                if isinstance(d, str):
                    from datetime import datetime
                    d = datetime.fromisoformat(d[:10]).date()
                if d < since: continue
                recs.append(r)
    except Exception:
        pass

    def _replay(w: dict) -> dict:
        import math as _math
        wins = 0; total = 0; ret_sum = 0.0
        pnls = []; cum = 0.0; peak = 0.0; maxdd = 0.0
        for r in recs:
            v = r.get("verdicts") or {}
            if not v: continue
            score = 0.0
            for name, verd in v.items():
                if name not in w: continue
                dir_ = verd.get("direction")
                if not dir_: continue
                try: dir_e = Direction(dir_)
                except Exception: continue
                score += _DIR.get(dir_e, 0.0) * verd.get("confidence", 0.5) * w[name]
            pred = "buy" if score > 0.05 else ("sell" if score < -0.05 else "hold")
            realized = r.get("realized_return")
            if realized is None: continue
            total += 1
            pnl = realized if pred == "buy" else (-realized if pred == "sell" else 0)
            pnls.append(pnl)
            ret_sum += pnl
            cum += pnl
            peak = max(peak, cum)
            maxdd = min(maxdd, cum - peak)
            if pnl > 0: wins += 1
        # Sharpe (annualized, 假设日频)
        sharpe = None
        if len(pnls) >= 3:
            mean = sum(pnls)/len(pnls)
            var = sum((p-mean)**2 for p in pnls)/max(1, len(pnls)-1)
            sd = _math.sqrt(var)
            if sd > 1e-9:
                sharpe = round((mean/sd) * _math.sqrt(252), 3)
        return {
            "n": total, "wins": wins,
            "win_rate": round(wins/total, 3) if total else None,
            "total_return": round(ret_sum, 4),
            "avg_return": round(ret_sum/total, 4) if total else None,
            "sharpe": sharpe,
            "max_drawdown": round(maxdd, 4),
        }

    resA, resB = _replay(wA), _replay(wB)
    # v0.10.0: paired bootstrap 显著性
    import random
    def _bootstrap_pvalue(recs_local: list, wA: dict, wB: dict, n_iter: int = 500) -> dict:
        if len(recs_local) < 8:
            return {"p_value": None, "ci_diff_low": None, "ci_diff_high": None, "n_iter": 0}
        # 对每条样本先算 (pnl_A - pnl_B) 差；然后 resample with replacement
        diffs_orig = []
        for r in recs_local:
            v = r.get("verdicts") or {}
            realized = r.get("realized_return")
            if realized is None or not v: continue
            def _pnl(w):
                score = 0.0
                for name, verd in v.items():
                    if name not in w: continue
                    try: d_e = Direction(verd.get("direction"))
                    except Exception: continue
                    score += _DIR.get(d_e, 0) * verd.get("confidence", 0.5) * w[name]
                pred = "buy" if score > 0.05 else ("sell" if score < -0.05 else "hold")
                return realized if pred == "buy" else (-realized if pred == "sell" else 0)
            diffs_orig.append(_pnl(wA) - _pnl(wB))
        if not diffs_orig: return {"p_value": None, "ci_diff_low": None, "ci_diff_high": None, "n_iter": 0}
        # bootstrap CI
        rng = random.Random(42)
        means = []
        n = len(diffs_orig)
        for _ in range(n_iter):
            m = sum(diffs_orig[rng.randint(0, n-1)] for _ in range(n)) / n
            means.append(m)
        means.sort()
        low, high = means[int(0.025*n_iter)], means[int(0.975*n_iter)]
        # 双侧 p-value: fraction where sign 与 orig_mean 相反
        orig_mean = sum(diffs_orig)/n
        if orig_mean == 0:
            p = 1.0
        else:
            same_side = sum(1 for m in means if (m > 0) == (orig_mean > 0))
            p = 2 * (1 - same_side/n_iter)
        return {"p_value": round(min(p, 1.0), 4), "ci_diff_low": round(low, 5),
                "ci_diff_high": round(high, 5), "n_iter": n_iter, "orig_mean_diff": round(orig_mean, 5)}

    boot = _bootstrap_pvalue(recs, wA, wB, n_iter=500)

    # walk-forward: 按时间分 4 段，每段独立比较
    walkfwd = []
    if len(recs) >= 8:
        recs_sorted = sorted(recs, key=lambda r: r.get("decision", {}).get("as_of", ""))
        n_folds = 4
        chunk = max(2, len(recs_sorted) // n_folds)
        for i in range(n_folds):
            fold = recs_sorted[i*chunk:(i+1)*chunk]
            if not fold: continue
            # 临时替换 recs 变量（简化：直接内联 replay）
            def _replay_fold(w):
                wins=total=0; ret=0
                for r in fold:
                    v = r.get("verdicts") or {}
                    realized = r.get("realized_return")
                    if realized is None or not v: continue
                    score = 0.0
                    for name, verd in v.items():
                        if name not in w: continue
                        try: de = Direction(verd.get("direction"))
                        except Exception: continue
                        score += _DIR.get(de,0) * verd.get("confidence",0.5) * w[name]
                    pred = "buy" if score>0.05 else ("sell" if score<-0.05 else "hold")
                    pnl = realized if pred=="buy" else (-realized if pred=="sell" else 0)
                    total += 1; ret += pnl
                    if pnl>0: wins += 1
                return {"n":total, "return": round(ret,4), "win_rate": round(wins/total,3) if total else None}
            rA, rB = _replay_fold(wA), _replay_fold(wB)
            walkfwd.append({"fold": i+1, "n": len(fold), "A": rA, "B": rB,
                             "winner": "A" if (rA["return"] or 0) > (rB["return"] or 0) else "B"})

    winner = "A" if (resA.get("avg_return") or 0) > (resB.get("avg_return") or 0) else "B"
    # 显著性标签
    sig_label = "N/A"
    if boot.get("p_value") is not None:
        p = boot["p_value"]
        sig_label = ("**significant**" if p < 0.05 else ("marginal" if p < 0.10 else "not significant"))
    return {
        "since": since.isoformat(), "days": days,
        "weights_A": wA, "weights_B": wB,
        "result_A": resA, "result_B": resB,
        "winner": winner if resA["n"] and resB["n"] else "N/A",
        "n_samples": resA["n"],
        "bootstrap": boot, "significance": sig_label,
        "walk_forward": walkfwd,
    }


AB_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>A/B 实验对比</title>
<style>body{font-family:-apple-system,SF Pro,sans-serif;background:#0d1117;color:#e6edf3;padding:20px}
h1{color:#58a6ff}h2{color:#f0883e}
.row{display:flex;gap:20px;margin:16px 0}
.card{flex:1;background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px}
.win{border:2px solid #3fb950}
label{display:block;color:#8b949e;margin:8px 0 4px}
input{background:#0d1117;color:#e6edf3;border:1px solid #30363d;padding:6px;border-radius:4px;width:100%}
button{background:#238636;color:#fff;border:0;padding:10px 20px;border-radius:5px;cursor:pointer;font-size:14px;margin-top:10px}
table{width:100%;border-collapse:collapse;margin-top:10px}
th,td{padding:6px 10px;text-align:left;border-bottom:1px solid #30363d}
.metric{font-size:24px;color:#3fb950}.neg{color:#f85149}
.pill{padding:2px 8px;border-radius:10px;font-size:12px}
.pill.a{background:#1f6feb}.pill.b{background:#8957e5}
a{color:#58a6ff}
</style></head><body>
<h1>🧪 A/B 实验对比 · StockOps</h1>
<p style="color:#8b949e">重放 memory 里的历史决策，比较两组分析师权重的累计收益/胜率。格式：<code>technical:0.4,fundamental:0.3,sentiment:0.1,macro_event:0.2</code></p>
<div class="row">
  <div class="card">
    <label>方案 A（默认=当前 configs/weights.yaml）</label>
    <input id="wA" placeholder="technical:0.35,fundamental:0.30,sentiment:0.15,macro_event:0.20"/>
  </div>
  <div class="card">
    <label>方案 B（默认=硬编码 default）</label>
    <input id="wB" placeholder="technical:0.40,fundamental:0.25,sentiment:0.20,macro_event:0.15"/>
  </div>
  <div class="card" style="flex:0.5">
    <label>回看天数</label>
    <input id="days" value="60" type="number"/>
    <button onclick="run()">▶ 开跑</button>
  </div>
</div>
<div id="results"></div>
<div style="margin-top:20px"><a href="/">← 返回主页</a> · <a href="/news">情报</a></div>
<script>
async function run(){
  const wA = document.getElementById('wA').value;
  const wB = document.getElementById('wB').value;
  const days = document.getElementById('days').value || '60';
  const params = new URLSearchParams({a:wA, b:wB, days});
  document.getElementById('results').innerHTML = '<p style="color:#8b949e">跑中...</p>';
  const r = await fetch('/api/ab?' + params).then(r=>r.json());
  const html = `
    <h2>结果 · 样本数=${r.n_samples} · 起始=${r.since}</h2>
    <div class="row">
      <div class="card ${r.winner==='A'?'win':''}">
        <span class="pill a">方案 A ${r.winner==='A'?' 🏆':''}</span>
        <p>累计收益 <span class="metric ${r.result_A.total_return>=0?'':'neg'}">${(r.result_A.total_return*100).toFixed(2)}%</span></p>
        <table><tr><th>胜率</th><td>${r.result_A.win_rate!==null?(r.result_A.win_rate*100).toFixed(1)+'%':'N/A'}</td></tr>
        <tr><th>平均单次</th><td>${r.result_A.avg_return!==null?(r.result_A.avg_return*100).toFixed(3)+'%':'N/A'}</td></tr>
        <tr><th>样本</th><td>${r.result_A.n}</td></tr>
        <tr><th>权重</th><td><pre style="margin:0;font-size:11px">${JSON.stringify(r.weights_A,null,2)}</pre></td></tr></table>
      </div>
      <div class="card ${r.winner==='B'?'win':''}">
        <span class="pill b">方案 B ${r.winner==='B'?' 🏆':''}</span>
        <p>累计收益 <span class="metric ${r.result_B.total_return>=0?'':'neg'}">${(r.result_B.total_return*100).toFixed(2)}%</span></p>
        <table><tr><th>胜率</th><td>${r.result_B.win_rate!==null?(r.result_B.win_rate*100).toFixed(1)+'%':'N/A'}</td></tr>
        <tr><th>平均单次</th><td>${r.result_B.avg_return!==null?(r.result_B.avg_return*100).toFixed(3)+'%':'N/A'}</td></tr>
        <tr><th>样本</th><td>${r.result_B.n}</td></tr>
        <tr><th>权重</th><td><pre style="margin:0;font-size:11px">${JSON.stringify(r.weights_B,null,2)}</pre></td></tr></table>
      </div>
    </div>
    <p style="color:#8b949e">回看天数 ${r.days} · winner=<b style="color:#3fb950">${r.winner}</b> · 显著性=<b>${r.significance||'N/A'}</b> (p=${(r.bootstrap&&r.bootstrap.p_value)||'N/A'})</p>
    ${r.bootstrap && r.bootstrap.n_iter ? `<div class="card"><b>📈 Bootstrap 95% CI of (A-B) mean-return:</b> [${(r.bootstrap.ci_diff_low*100).toFixed(3)}%, ${(r.bootstrap.ci_diff_high*100).toFixed(3)}%] · n_iter=${r.bootstrap.n_iter} · orig_mean_diff=${(r.bootstrap.orig_mean_diff*100).toFixed(4)}%</div>` : ''}
    ${r.walk_forward && r.walk_forward.length ? `<h2>🚶 Walk-forward (${r.walk_forward.length} folds)</h2><table><tr><th>Fold</th><th>N</th><th>A return</th><th>B return</th><th>Winner</th></tr>${r.walk_forward.map(w=>'<tr><td>'+w.fold+'</td><td>'+w.n+'</td><td>'+(w.A.return*100).toFixed(2)+'%</td><td>'+(w.B.return*100).toFixed(2)+'%</td><td class="pill '+(w.winner==='A'?'a':'b')+'">'+w.winner+'</td></tr>').join('')}</table>` : ''}
  `;
  document.getElementById('results').innerHTML = html;
}
</script></body></html>"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    srv = HTTPServer((args.host, args.port), Handler)
    print(f"[dashboard] http://{args.host}:{args.port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()




# ============== Advise 一站式看板（v0.13.0） ==============
def _advise_sync(params: dict) -> dict:
    import asyncio
    from datetime import date
    from tools.advise_pipeline import run_advise
    tickers = [t.strip() for t in (params.get("tickers", ["AAPL"])[0]).split(",") if t.strip()]
    equity = float(params.get("equity", ["100000"])[0])
    as_of = date.today()
    if params.get("date"):
        try: as_of = date.fromisoformat(params["date"][0])
        except Exception: pass
    include_bt = params.get("bt", ["0"])[0] in ("1", "true", "on")
    use_llm = params.get("llm", ["0"])[0] in ("1", "true", "on")
    try:
        out = asyncio.run(run_advise(tickers, as_of, equity, include_backtest=include_bt, use_llm=use_llm))
        return {"ok": True, "markdown": out.get("markdown", ""), "overview": out.get("overview")}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


ADVISE_HTML = """<!doctype html><html><head><meta charset=\"utf-8\"><title>Advise 建议</title>
<style>
body{background:#0d1117;color:#e6e6e6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;margin:0;padding:20px;line-height:1.5}
input,button{padding:6px 10px;background:#161b22;color:#e6e6e6;border:1px solid #30363d;border-radius:4px;font-size:13px}
button{cursor:pointer;background:#1f6feb;border:none}
button:hover{background:#388bfd}
.wrap{max-width:1200px;margin:auto}
#out{background:#161b22;padding:16px;border-radius:6px;border:1px solid #30363d;overflow:auto;max-height:75vh}
#out h1,#out h2{color:#7ee787;border-bottom:1px solid #30363d;padding-bottom:4px}
#out table{border-collapse:collapse;margin:6px 0}
#out td,#out th{border:1px solid #30363d;padding:4px 8px}
.row{display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
a{color:#58a6ff}
</style></head><body><div class=wrap>
<div class=row><a href='/'>← 返回</a>
<input id=tk value=\"600519.SS,AAPL,0700.HK\" style=width:340px>
<input id=eq value=\"100000\" style=width:100px>
<label><input type=checkbox id=bt> +历史回测</label>
<label><input type=checkbox id=llm> +LLM 综合</label>
<button onclick=go()>生成建议</button> <button onclick=push()>推送到微信/飞书</button>
<span id=st style='color:#8b949e'></span>
</div>
<div id=out>请点击「生成建议」...</div>
<script>
async function push(){
  const tk=document.getElementById('tk').value;
  const eq=document.getElementById('eq').value;
  document.getElementById('st').textContent='推送中...';
  const r=await fetch('/api/notify?tickers='+encodeURIComponent(tk)+'&equity='+eq);
  const j=await r.json();
  document.getElementById('st').textContent=j.ok?('已推送: '+JSON.stringify(j.channels)):('错误: '+(j.error||''));
}
async function go(){
  const tk=document.getElementById('tk').value;
  const eq=document.getElementById('eq').value;
  const bt=document.getElementById('bt').checked?1:0;
  const llm=document.getElementById('llm').checked?1:0;
  document.getElementById('st').textContent='跑分析师中...';
  const r=await fetch('/api/advise?tickers='+encodeURIComponent(tk)+'&equity='+eq+'&bt='+bt+'&llm='+llm);
  const j=await r.json();
  if(!j.ok){document.getElementById('out').innerHTML='<pre style=color:#f85149>'+(j.error||'unknown')+'</pre>';document.getElementById('st').textContent='错误';return;}
  document.getElementById('out').innerHTML=render(j.markdown);
  document.getElementById('st').textContent='完成';
}
function render(md){
  // 极简 md 转 html
  let h=md.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  h=h.replace(/^# (.+)$/gm,'<h1>$1</h1>');
  h=h.replace(/^## (.+)$/gm,'<h2>$1</h2>');
  h=h.replace(/\\*\\*(.+?)\\*\\*/g,'<b>$1</b>');
  h=h.replace(/^- (.+)$/gm,'<li>$1</li>');
  h=h.replace(/\\n\\n/g,'<br>');
  h=h.replace(/\\n/g,'<br>');
  return h;
}
</script></div></body></html>"""

if __name__ == "__main__":
    main()
