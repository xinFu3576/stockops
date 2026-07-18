"""飞书/邮件推送。可选:通过环境变量启用。
- FEISHU_WEBHOOK: 自定义机器人 webhook URL(不填则跳过)
- FEISHU_SECRET:  签名密钥(可选)
- SMTP_HOST/SMTP_USER/SMTP_PASS/SMTP_TO: 简单邮件(可选)
入口:
  python -m tools.notify --title "StockOps Alert" --body-file reports/alert_xxx.md
"""
from __future__ import annotations
import argparse, base64, hashlib, hmac, json, os, ssl, time, urllib.request, urllib.error


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


def notify(title: str, body: str) -> dict:
    return {"feishu": send_feishu(title, body), "smtp": send_smtp(title, body)}


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
        print("[notify] 所有通道均未配置或均失败(未设置 FEISHU_WEBHOOK / SMTP_*)")


if __name__ == "__main__":
    main()
