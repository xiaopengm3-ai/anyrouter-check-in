#!/usr/bin/env python3
"""FutureHub 每日签到

站点登录页有 Cloudflare Turnstile，纯 HTTP 登录过不去，
因此优先用 session cookie（FUTUREHUB_SESSION），失效才回落到密码登录。
"""

import json
import os
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from email.header import Header
from email.mime.text import MIMEText

BASE = os.environ.get("FUTUREHUB_BASE", "https://api.futureppo.top").rstrip("/")
USER = os.environ.get("FUTUREHUB_USER", "")
PASS = os.environ.get("FUTUREHUB_PASS", "")
SESSION = os.environ.get("FUTUREHUB_SESSION", "").strip()
UID = os.environ.get("FUTUREHUB_UID", "").strip()
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")


def notify_fail(subject: str, body: str) -> None:
    """失败时发邮件（配置了 EMAIL_USER/EMAIL_PASS 才发）。"""
    user = os.environ.get("EMAIL_USER", "")
    pwd = os.environ.get("EMAIL_PASS", "")
    to = os.environ.get("EMAIL_TO", "") or user
    host = os.environ.get("CUSTOM_SMTP_SERVER", "") or (
        f"smtp.{user.split('@')[1]}" if "@" in user else "")
    if not (user and pwd and host):
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = user
    msg["To"] = to
    try:
        with smtplib.SMTP_SSL(host, 465, context=ssl.create_default_context(), timeout=25) as srv:
            srv.login(user, pwd)
            srv.sendmail(user, [to], msg.as_string())
        print("[MAIL] 已发送失败通知")
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] 邮件发送失败: {type(exc).__name__}: {exc}")


def req(path, payload=None, cookie=None, uid=None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(BASE + path, data=data, method="POST" if data else "GET")
    r.add_header("User-Agent", UA)
    r.add_header("Accept", "application/json")
    if data:
        r.add_header("Content-Type", "application/json")
    if cookie:
        r.add_header("Cookie", f"session={cookie}")
    if uid:
        r.add_header("new-api-user", str(uid))
    try:
        with urllib.request.urlopen(r, timeout=25) as resp:
            raw = resp.read().decode("utf-8", "replace")
            sc = resp.headers.get_all("Set-Cookie") or []
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        sc = exc.headers.get_all("Set-Cookie") or []
    try:
        return json.loads(raw), sc
    except json.JSONDecodeError:
        return {"_raw": raw[:200]}, sc


def main():
    cookie, uid = None, (int(UID) if UID.isdigit() else None)

    if SESSION:
        body, _ = req("/api/user/self", None, SESSION, uid)
        if body.get("success"):
            d = body.get("data") or {}
            uid = d.get("id") or uid
            print(f"[OK] 用 cookie 登录态，用户={d.get('username')} id={uid}")
            cookie = SESSION
        else:
            print(f"[WARN] cookie 失效: {body.get('message')} raw={str(body)[:400]}")
            notify_fail("【xectro】FutureHub cookie 已失效",
                        f"cookie 验证失败：{body.get('message')}\n\n"
                        "请重新登录 api.futureppo.top，复制 session cookie 更新 GitHub Secret FUTUREHUB_SESSION。")

    if not cookie:
        if not USER or not PASS:
            print("[FAIL] 没有可用 cookie，也没配账号密码")
            return 1
        body, headers = req("/api/user/login", {"username": USER, "password": PASS})
        if not body.get("success"):
            print(f"[FAIL] 登录失败（站点可能要 Turnstile）: {body.get('message')} raw={str(body)[:400]}")
            return 1
        uid = body.get("data", {}).get("id")
        cookie = next((h.split("session=", 1)[1].split(";", 1)[0]
                       for h in headers if "session=" in h), "")
        print(f"[OK] 密码登录成功 id={uid}")

    r, _ = req("/api/user/checkin", {}, cookie, uid)
    msg = r.get("message", "")
    if r.get("success"):
        print(f"[SUCCESS] 签到成功: {msg}")
    elif "已签到" in str(msg):
        print(f"[SKIP] {msg}")
    else:
        print(f"[FAIL] 签到失败: {r}")
        notify_fail("【xectro】FutureHub 签到失败", f"接口返回：{r}")
        return 1

    s, _ = req("/api/user/self", None, cookie, uid)
    d = s.get("data", {})
    print(f"[BALANCE] 余额={d.get('quota')} 已用={d.get('used_quota')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
