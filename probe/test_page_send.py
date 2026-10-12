#!/usr/bin/env python3
"""页面真发测试：用户本人号，真 Chrome TLS 发送（绕 JA3）。"""
import sys, json, urllib.parse
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
import httpx
from app.upstream.dola.send_body import build_completion_body
from app.upstream.dola.signer import SignerClient

signer = SignerClient("http://127.0.0.1:8491", timeout=150)

COOKIE = open('/Users/betterme/PycharmProjects/AI/reverse/dola/probe/.user_own_cookie').read().strip()
mst = ""
for part in COOKIE.split(";"):
    if part.strip().startswith("msToken="):
        mst = part.strip().split("=", 1)[1]

Q = ("version_code=20800&language=zh&device_platform=web&doubao_device_platform=web"
     "&fp=verify_mv277m3x_92nktDso_Rc2g_41Ql_8FYI_BcR44nhazpMY"
     "&aid=495671&device_id=7694970144608241157&web_id=7694973274530743813"
     "&doubao_pc_version=3.39.1&pc_version=3.39.1&pkg_type=release_version"
     "&real_aid=495671&region=TW&samantha_web=1&sys_region=TW"
     "&tea_uuid=7694973274530743813&tz_name=Asia%2FShanghai"
     "&use-olympus-account=1&web_platform=browser"
     "&web_tab_id=fd14c83a-f2e9-4d36-9235-403b1493e877"
     f"&msToken={urllib.parse.quote(mst)}")
url = f"https://www.dola.com/chat/completion?{Q}"

ap = {"model": "seedance_v2.5", "duration": 10,
      "input_box_content": {"user_input_content": "页面真发验证：雪山日出延时",
                            "reply_message_format": "生成视频：%s"}}
body = json.dumps(build_completion_body(prompt="页面真发验证：雪山日出延时",
                                        skill_type=17, ability_param=ap),
                  ensure_ascii=False)
signed = signer.sign(url, body, force=True)
print("minted:", "a_bogus ok" if "a_bogus=" in signed else "MISSING")

# 页面真发（Chrome 内 fetch —— 真 TLS + 真指纹 + credentials:include）
# 注意：signer 的 Chrome 本身在国内网络 → Chrome 走系统代理（用户代理在系统层，应该能出去）
r = httpx.post("http://127.0.0.1:8491/send", timeout=90,
               json={"cookie": COOKIE, "url": signed, "body": body})
out = r.json().get("sse_head", "")
print("SSE head:", out[:300])

if "SSE_ACK" in out:
    try:
        for seg in out.split("\n"):
            if seg.startswith("data:") and "SSE_ACK" in seg:
                d = json.loads(seg.split(":", 1)[1].strip())
                conv = d.get("ack_client_meta", {}).get("conversation_id", "")
                print("CONV:", conv)
                break
    except Exception:
        pass
