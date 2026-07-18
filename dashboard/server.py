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
<h1>📈 StockOps · 团队仪表盘 <small style="color:#7d8590">v0.4.0</small></h1>
<div style="margin-bottom:16px"><input id="chartTk" placeholder="600519.SS" size="20"/><button onclick="window.open('/chart/'+encodeURIComponent(document.getElementById('chartTk').value||'AAPL'),'_blank')" style="background:#1f6feb;color:#fff;border:0;padding:6px 12px;border-radius:5px;cursor:pointer;margin-left:8px">🕯 打开 K 线</button></div>
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
        return self._send(404, "not found", "text/plain")


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


if __name__ == "__main__":
    main()
