#!/usr/bin/env python3
"""msToken 决定性验证：活 msToken 拼 query+cookie，in-02 发送。"""
import sys, json, urllib.request
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
import httpx
from app.upstream.dola.send_body import build_completion_body
from app.upstream.dola.client import DolaClient
from app.upstream.dola.signer import SignerClient

signer = SignerClient("http://127.0.0.1:8491", timeout=150)

# 活 msToken + 活 UA（来自 signer 的真实 Chrome 页面）
info = httpx.get("http://127.0.0.1:8491/pageinfo", timeout=10).json()
ms = info["msToken"]
UA = info["ua"]
print(f"msToken: {len(ms)} chars | UA: {UA[:50]}")

accounts = json.load(open('/Users/betterme/PycharmProjects/AI/reverse/dola/data/accounts.local.json'))
acct = {a['name']: a for a in accounts}['acct-in-02']

# URL 带 msToken（在 a_bogus 之前——浏览器顺序：...&msToken=xxx&a_bogus=yyy）
BASE_Q = ("version_code=20800&language=zh&device_platform=web&doubao_device_platform=web"
          "&fp=verify_mv277m3x_92nktDso_Rc2g_41Ql_8FYI_BcR44nhazpMY"
          "&aid=495671&device_id=7694970144608241157&web_id=7694970157622462005"
          "&doubao_pc_version=3.39.1&pc_version=3.39.1&pkg_type=release_version"
          "&real_aid=495671&region=TW&samantha_web=1&sys_region=TW"
          "&tea_uuid=7694970157622462005&tz_name=Asia%2FShanghai"
          "&use-olympus-account=1&web_platform=browser"
          "&web_tab_id=fd14c83a-f2e9-4d36-9235-403b1493e877")
url = f"https://www.dola.com/chat/completion?{BASE_Q}&msToken={urllib.parse.quote(ms)}"

ap = {"model": "seedance_v2.5", "duration": 10,
      "input_box_content": {"user_input_content": "msToken验证",
                            "reply_message_format": "生成视频：%s"}}
body = json.dumps(build_completion_body(prompt="msToken验证", skill_type=17,
                                        ability_param=ap), ensure_ascii=False)
signed = signer.sign(url, body, force=True)
print("minted:", "a_bogus ok" if "a_bogus=" in signed else "MISSING")

# cookie 附加 msToken（浏览器行为）
cookie_full = acct["cookie"] + f";msToken={ms}"

verdict, conv = None, ""
with httpx.stream("POST", signed, content=body.encode(), proxy="http://127.0.0.1:57890",
                  headers={"content-type": "application/json; encoding=utf-8",
                           "cookie": cookie_full,
                           "user-agent": UA}, timeout=30) as resp:
    ct = resp.headers.get("content-type", "")
    if "event-stream" not in ct:
        body_bytes = b""
        for chunk in resp.iter_bytes():
            body_bytes += chunk
        verdict = f"HTTP {resp.status_code} {body_bytes[:120]}"
    else:
        for line in resp.iter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].strip()
                if event == "STREAM_ERROR":
                    try:
                        e = json.loads(data)
                        verdict = f"{e.get('error_code')} {e.get('error_msg','')[:50]}"
                    except Exception:
                        verdict = data[:70]
                    break
                if event == "SSE_ACK":
                    conv = json.loads(data).get("ack_client_meta", {}).get("conversation_id", "")
                    verdict = f"🎉 ACCEPTED conv={conv}"
                    break

print("VERDICT:", verdict)
