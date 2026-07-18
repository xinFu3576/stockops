"""Knowledge Base 写入器 v0.15：advise + 执行结果 → 本地 KB / Notion / Confluence / GitHub Issue。

三级降级：
1. 本地 markdown 归档 (reports/kb/YYYY/MM/YYYY-MM-DD.md) — 始终写
2. Notion (NOTION_TOKEN + NOTION_DB_ID)
3. Confluence (CONFLUENCE_URL + CONFLUENCE_USER + CONFLUENCE_TOKEN + CONFLUENCE_SPACE)
4. GitHub Issue (GH_KB_REPO + GH_TOKEN — 用作简易 KB)

用法：
    from tools.knowledge_base import archive_daily_advise
    archive_daily_advise(as_of, markdown_body, exec_results=None)
"""
from __future__ import annotations
import os, json, base64, pathlib, urllib.request, urllib.parse, ssl
from datetime import date, datetime
from typing import Optional

_CTX = ssl.create_default_context()
ROOT = pathlib.Path(__file__).resolve().parents[1]
KB_DIR = ROOT / "reports" / "kb"


def _http(method: str, url: str, headers: dict, body: bytes | None = None, timeout: float = 15.0):
    req = urllib.request.Request(url, method=method, headers=headers, data=body)
    r = urllib.request.urlopen(req, context=_CTX, timeout=timeout)
    return r.status, r.read().decode(errors="ignore")


def write_local(as_of, markdown: str) -> str:
    """始终写：本地 KB 归档。"""
    d = as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of))
    outdir = KB_DIR / f"{d.year:04d}" / f"{d.month:02d}"
    outdir.mkdir(parents=True, exist_ok=True)
    fp = outdir / f"{d.isoformat()}.md"
    fp.write_text(markdown, encoding="utf-8")
    idx = KB_DIR / "INDEX.md"
    line = f"- [{d.isoformat()}](./{d.year:04d}/{d.month:02d}/{d.isoformat()}.md)\n"
    if idx.exists():
        cur = idx.read_text()
        if line not in cur:
            idx.write_text(line + cur)
    else:
        idx.write_text("# StockOps Knowledge Base\n\n" + line)
    return str(fp)


def write_notion(as_of, title: str, markdown: str) -> dict:
    """POST 到 Notion 数据库。需要 NOTION_TOKEN + NOTION_DB_ID。"""
    token = os.environ.get("NOTION_TOKEN")
    db = os.environ.get("NOTION_DB_ID")
    if not token or not db:
        return {"ok": False, "reason": "NOTION_TOKEN/NOTION_DB_ID 未配置"}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }
    # 拆 markdown 成 blocks（简易：按行）
    blocks = []
    for line in markdown.splitlines()[:100]:   # notion 单请求 100 blocks 上限
        if not line.strip():
            continue
        blocks.append({
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": line[:1900]}}]},
        })
    payload = {
        "parent": {"database_id": db},
        "properties": {
            "Name": {"title": [{"text": {"content": title}}]},
        },
        "children": blocks,
    }
    try:
        status, body = _http("POST", "https://api.notion.com/v1/pages",
                             headers=headers, body=json.dumps(payload).encode())
        return {"ok": 200 <= status < 300, "status": status, "response": body[:200]}
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def write_confluence(as_of, title: str, markdown: str) -> dict:
    url = os.environ.get("CONFLUENCE_URL")
    user = os.environ.get("CONFLUENCE_USER")
    tok = os.environ.get("CONFLUENCE_TOKEN")
    space = os.environ.get("CONFLUENCE_SPACE")
    if not (url and user and tok and space):
        return {"ok": False, "reason": "Confluence 配置不完整"}
    endpoint = f"{url.rstrip('/')}/rest/api/content"
    auth = base64.b64encode(f"{user}:{tok}".encode()).decode()
    headers = {"Authorization": f"Basic {auth}", "Content-Type": "application/json"}
    # 极简 markdown → storage：换行转 <p>
    html = "".join(f"<p>{line.replace('<', '&lt;').replace('>', '&gt;')}</p>" for line in markdown.splitlines() if line.strip())
    payload = {
        "type": "page", "title": title,
        "space": {"key": space},
        "body": {"storage": {"value": html, "representation": "storage"}},
    }
    try:
        status, body = _http("POST", endpoint, headers=headers, body=json.dumps(payload).encode())
        return {"ok": 200 <= status < 300, "status": status, "response": body[:200]}
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def write_github_issue(as_of, title: str, markdown: str) -> dict:
    """开一个 Issue 到 GH_KB_REPO 存档。"""
    repo = os.environ.get("GH_KB_REPO") or os.environ.get("GITHUB_KB_REPO")
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not (repo and tok):
        return {"ok": False, "reason": "GH_KB_REPO/GH_TOKEN 未配置"}
    headers = {"Authorization": f"token {tok}",
               "Accept": "application/vnd.github+json",
               "Content-Type": "application/json"}
    payload = {"title": title, "body": markdown[:60000], "labels": ["advise"]}
    try:
        status, body = _http("POST", f"https://api.github.com/repos/{repo}/issues",
                             headers=headers, body=json.dumps(payload).encode())
        return {"ok": 200 <= status < 300, "status": status, "response": body[:200]}
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def archive_daily_advise(as_of, markdown_body: str, exec_results: list | None = None) -> dict:
    """一次性把 advise + 执行结果写到所有已配置的 KB。"""
    d = as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of))
    body = markdown_body
    if exec_results:
        body += "\n\n## 🧾 执行结果\n\n"
        body += "| Ticker | Side | Qty | Price | Status | Reason |\n"
        body += "|---|---|---|---|---|---|\n"
        for r in exec_results:
            body += (f"| {r.get('ticker','-')} | {r.get('side','-')} | "
                     f"{r.get('qty','-')} | {r.get('price','-')} | "
                     f"{r.get('status','-')} | {(r.get('reason') or '')[:60]} |\n")
    title = f"StockOps 交易建议 · {d.isoformat()}"
    results = {"local": write_local(d, body)}
    if os.environ.get("NOTION_TOKEN"):
        results["notion"] = write_notion(d, title, body)
    if os.environ.get("CONFLUENCE_TOKEN"):
        results["confluence"] = write_confluence(d, title, body)
    if os.environ.get("GH_KB_REPO"):
        results["github"] = write_github_issue(d, title, body)
    return results


if __name__ == "__main__":
    import sys
    as_of = date.today() if len(sys.argv) < 2 else date.fromisoformat(sys.argv[1])
    body = sys.stdin.read()
    r = archive_daily_advise(as_of, body)
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
