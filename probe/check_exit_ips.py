#!/usr/bin/env python3
"""验证每账号粘性代理：各账号名的实际出口 IP。"""
import sys, json
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
import httpx

POOL = "socks5h://poolclient-{acct}:Aq68C0iU8x0qFBYP@pool.livetest.cn:2090"
for acct in ["acct-tw-01", "acct-in-02", "new-sv-01", "new-iq-02"]:
    proxy = POOL.format(acct=acct)
    try:
        with httpx.Client(proxy=proxy, timeout=15) as c:
            r = c.get("https://api.ipify.org?format=json")
            ip = r.json().get("ip", "?")
        print(f"{acct}: exit IP = {ip}")
    except Exception as e:
        print(f"{acct}: PROXY ERR {type(e).__name__}: {str(e)[:80]}")
