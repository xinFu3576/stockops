#!/usr/bin/env bash
# 一键把 StockOps 装到目标机器的 OpenClaw
set -euo pipefail
PLUGIN_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$PLUGIN_DIR")"
HOME_DIR="${HOME}"

echo "== StockOps 部署 =="
echo "项目根: $PROJECT_DIR"

# 1. skills
echo "-- 1. 安装 skills 到 ~/.openclaw/skills/"
mkdir -p "$HOME_DIR/.openclaw/skills"
for d in "$PROJECT_DIR"/skills/stockops-*; do
  n=$(basename "$d")
  rm -rf "$HOME_DIR/.openclaw/skills/$n"
  cp -R "$d" "$HOME_DIR/.openclaw/skills/$n"
done

# 2. workspaces
echo "-- 2. 安装 workspaces 到 ~/.openclaw/workspace/workspaces/stockops/"
mkdir -p "$HOME_DIR/.openclaw/workspace/workspaces/stockops"
cp -R "$PLUGIN_DIR"/openclaw_workspaces/* "$HOME_DIR/.openclaw/workspace/workspaces/stockops/"

# 3. agent dirs
echo "-- 3. 建 agentDir 占位"
for id in stockops_operator stock_data stock_analyst stock_backtest stock_risk stock_execution stock_reflection stock_observability; do
  mkdir -p "$HOME_DIR/.openclaw/workspace/agents/$id/agent"
done

# 4. openclaw.json 合并(需人工确认后再改;这里只打印片段)
echo "-- 4. openclaw.json 片段 (要合并):"
python3 -c "
import json
stubs=json.load(open('$PLUGIN_DIR/openclaw_agents.stub.json'))['agents']
h='$HOME_DIR'
for a in stubs:
    a['workspace']=a['workspace'].replace('{{HOME}}',h)
    a['agentDir']=a['agentDir'].replace('{{HOME}}',h)
print(json.dumps({'agents':{'list_appended':stubs}}, ensure_ascii=False, indent=2))
"

echo ""
echo "== 完成:请把上面 agents 片段合并进 ~/.openclaw/openclaw.json 的 agents.list =="
echo "== 或运行 ./install.sh --merge 自动合并(会先备份) =="

if [[ "${1:-}" == "--merge" ]]; then
  BK="$HOME_DIR/.openclaw/openclaw.json.bak-stockops-$(date +%Y%m%d-%H%M%S)"
  cp "$HOME_DIR/.openclaw/openclaw.json" "$BK"
  python3 - <<PYEND
import json, os
h=os.environ['HOME']
cfg=json.load(open(f'{h}/.openclaw/openclaw.json'))
stubs=json.load(open('$PLUGIN_DIR/openclaw_agents.stub.json'))['agents']
existing={a['id'] for a in cfg['agents']['list']}
added=0
for a in stubs:
  if a['id'] in existing: continue
  a['workspace']=a['workspace'].replace('{{HOME}}',h)
  a['agentDir']=a['agentDir'].replace('{{HOME}}',h)
  cfg['agents']['list'].append(a); added+=1
json.dump(cfg,open(f'{h}/.openclaw/openclaw.json','w'),ensure_ascii=False,indent=2)
print(f'[merge] 追加 {added} 个 agent,备份于 $BK')
PYEND
fi

echo "-- 5. Python 依赖: cd '$PROJECT_DIR' && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt"
