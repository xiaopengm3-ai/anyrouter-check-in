#!/usr/bin/env python3
"""FutureHub（NewAPI）每日签到

不依赖浏览器，直接走 API：
  1. POST /api/user/login   → 拿 session cookie 和用户 id
  2. POST /api/user/checkin → 签到（带 new-api-user 头）
  3. GET  /api/user/self    → 打印余额

环境变量：
  FUTUREHUB_BASE    站点地址，默认 https://api.futureppo.top
  FUTUREHUB_USER    用户名或邮箱
  FUTUREHUB_PASS    密码
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("FUTUREHUB_BASE", "https://api.futureppo.top").rstrip("/")
USER = os.environ.get("FUTUREHUB_USER", "")
PASS = os.environ.get("FUTUREHUB_PASS", "")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"


def request(path: str, *, payload: dict | None = None, cookie: str | None = None,
            user_id: int | None = None) -> tuple[int, dict, list[str]]:
    url = f"{BASE}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "application/json")
    if data:
        req.add_header("Content-Type", "application/json")
    if cookie:
        req.add_header("Cookie", f"session={cookie}")
    if user_id:
        req.add_header("new-api-user", str(user_id))

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", "replace")
            headers = resp.headers.get_all("Set-Cookie") or []
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        headers = exc.headers.get_all("Set-Cookie") or []
        status = exc.code

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = {"_raw": body[:300]}
    return status, parsed, headers


def main() -> int:
    if not USER or not PASS:
        print("[FAIL] 缺少 FUTUREHUB_USER / FUTUREHUB_PASS", file=sys.stderr)
        return 1

    print(f"[INFO] 登录 {BASE} 用户 {USER}")
    status, body, headers = request("/api/user/login", payload={"username": USER, "password": PASS})
    if not body.get("success"):
        print(f"[FAIL] 登录失败 status={status} body={body}")
        return 1

    user_id = body.get("data", {}).get("id")
    session = ""
    for raw in headers:
        if raw.lower().startswith("session=") or "; session=" in raw.lower():
            session = raw.split("session=", 1)[1].split(";", 1)[0]
            break
    if not session or not user_id:
        print(f"[FAIL] 没拿到 session 或用户 id: session={bool(session)} id={user_id}")
        return 1
    print(f"[OK] 登录成功 id={user_id}")

    print("[INFO] 执行签到")
    status, body, _ = request("/api/user/checkin", payload={}, cookie=session, user_id=user_id)
    message = body.get("message", "") or body.get("_raw", "")
    if body.get("success"):
        print(f"[SUCCESS] 签到成功: {message}")
    elif "已签到" in str(message):
        print(f"[SKIP] {message}")
    else:
        print(f"[FAIL] 签到失败 status={status} body={body}")
        return 1

    _, self_body, _ = request("/api/user/self", cookie=session, user_id=user_id)
    data = self_body.get("data", {})
    quota = data.get("quota")
    used = data.get("used_quota")
    print(f"[BALANCE] 用户名={data.get('username')} 余额={quota} 已用={used}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
