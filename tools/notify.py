"""飞书/邮件/企业微信/Server 酱 推送。可选:通过环境变量启用。
- FEISHU_WEBHOOK: 飞书自定义机器人 (不填则跳过)
- FEISHU_SECRET:  飞书签名密钥 (可选)
- WECOM_WEBHOOK:  企业微信群机器人 webhook (推荐,免申请)
- WECOM_MENTION:  企业微信 @人 手机号或 all,逗号分隔 (可选)
- SERVERCHAN_KEY: Server 酱 SendKey (个人微信推送,免服务器)
- SMTP_HOST/SMTP_USER/SMTP_PASS/SMTP_TO: 简单邮件(可选)
入口:
  python -m tools.notify --title "StockOps Alert" --body-file reports/alert_xxx.md
"""
from __future__ import annotations
import argparse, base64, hashlib, hmac, json, os, ssl, time, urllib.error, urllib.parse, urllib.request


def _feishu_sign(secret: str, ts: int) -> str:
    to_sign = f"{ts}\n{secret}".encode()
    h = hmac.new(to_sign, digestmod=hashlib.sha256).digest()
    return base64.b64encode(h).decode()


def send_feishu(title: str, body: str) -> bool:
    url = os.environ.get("FEISHU_WEBHOOK")
    if not url:
        return False
    secret = os.environ.get("FEISHU_SECRET")
    payload = {"msg_type": "text", "content": {"text": f"【{title}】\n\n{body[:4000]}"}}
    if secret:
        ts = int(time.time())
        payload["timestamp"] = str(ts)
        payload["sign"] = _feishu_sign(secret, ts)
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=15)
        return r.status == 200
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"[notify] feishu 失败: {e}")
        return False


def send_smtp(title: str, body: str) -> bool:
    host = os.environ.get("SMTP_HOST")
    to = os.environ.get("SMTP_TO")
    if not (host and to):
        return False
    import smtplib
    from email.mime.text import MIMEText
    user = os.environ.get("SMTP_USER", "")
    pw = os.environ.get("SMTP_PASS", "")
    port = int(os.environ.get("SMTP_PORT", "465"))
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = title
    msg["From"] = user or host
    msg["To"] = to
    try:
        with smtplib.SMTP_SSL(host, port, timeout=15) as s:
            if user:
                s.login(user, pw)
            s.sendmail(msg["From"], [to], msg.as_string())
        return True
    except Exception as e:
        print(f"[notify] smtp 失败: {e}")
        return False



def format_notification(title: str, sections: dict, footer: str = '') -> str:
    """统一美化的通知模板：emoji 分区 + 汇总。sections dict: 名字→str/list."""
    _EMOJI = {"决策":"🎯","风险":"⚠️","数据":"📊","情报":"📰","执行":"⚡","账户":"💰","复盘":"🔍"}
    lines = [f"### 📌 {title}", ""]
    for name, val in sections.items():
        emoji = _EMOJI.get(name, "•")
        lines.append(f"**{emoji} {name}**")
        if isinstance(val, (list, tuple)):
            for v in val:
                lines.append(f"- {v}")
        else:
            lines.append(str(val))
        lines.append("")
    if footer:
        lines.append(f"---\n_{footer}_")
    return "\n".join(lines)


def send_wecom(title: str, body: str) -> bool:
    """企业微信群机器人 webhook: 免申请,内部群 / 外部群都能用。
    支持 @群成员(WECOM_MENTION=13800138000,或 @all)。
    """
    url = os.environ.get("WECOM_WEBHOOK")
    if not url:
        return False
    mentions = [m.strip() for m in (os.environ.get("WECOM_MENTION", "") or "").split(",") if m.strip()]
    at_all = "@all" in mentions or "all" in mentions
    numeric = [m for m in mentions if m.isdigit()]
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": f"### {title}\n\n{body[:3800]}",
        }
    }
    if numeric or at_all:
        # markdown 消息用 <@手机号> 语法在正文里嵌入
        extra = " ".join([f"<@{m}>" for m in numeric])
        if at_all: extra = "<@all> " + extra
        payload["markdown"]["content"] = extra + "\n\n" + payload["markdown"]["content"]
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=15)
        if r.status != 200: return False
        resp = json.loads(r.read().decode())
        return int(resp.get("errcode", 0)) == 0
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        print(f"[notify] wecom 失败: {e}")
        return False


def send_serverchan(title: str, body: str) -> bool:
    """Server 酱: 用 SendKey 推到个人微信,无需服务器。
    key 从 https://sct.ftqq.com 获取。
    """
    key = os.environ.get("SERVERCHAN_KEY")
    if not key: return False
    # sct.ftqq.com 用 SCT 前缀; ft.com 用普通 key
    url = f"https://sctapi.ftqq.com/{key}.send"
    data = urllib.parse.urlencode({
        "title": title[:32],  # 限 32 字符
        "desp": body[:32700],  # 限 32KB
    }).encode()
    req = urllib.request.Request(url, data=data)
    try:
        r = urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=15)
        if r.status != 200: return False
        resp = json.loads(r.read().decode())
        return int(resp.get("code", -1)) == 0
    except Exception as e:
        print(f"[notify] serverchan 失败: {e}")
        return False


def notify(title: str, body: str) -> dict:
    return {
        "feishu": send_feishu(title, body),
        "wecom": send_wecom(title, body),
        "serverchan": send_serverchan(title, body),
        "smtp": send_smtp(title, body),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--body", default="")
    ap.add_argument("--body-file")
    args = ap.parse_args()
    body = args.body
    if args.body_file:
        body = open(args.body_file).read()
    res = notify(args.title, body)
    print("[notify] result:", res)
    if not any(res.values()):
        print("[notify] 所有通道均未配置或均失败(未设置 FEISHU_WEBHOOK / WECOM_WEBHOOK / SERVERCHAN_KEY / SMTP_*)")


if __name__ == "__main__":
    main()
