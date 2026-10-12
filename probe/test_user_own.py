#!/usr/bin/env python3
"""用户本人账号决定性测试：最高保真复刻浏览器请求。"""
import sys, json, urllib.parse
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
import httpx
from app.upstream.dola.send_body import build_completion_body
from app.upstream.dola.signer import SignerClient

signer = SignerClient("http://127.0.0.1:8491", timeout=150)

COOKIE = open('/Users/betterme/PycharmProjects/AI/reverse/dola/probe/.user_own_cookie').read().strip()
# 从 cookie 里取 msToken
mst = ""
for part in COOKIE.split(";"):
    if part.strip().startswith("msToken="):
        mst = part.strip().split("=", 1)[1]
print(f"cookie len: {len(COOKIE)} | msToken: {len(mst)} chars")

# 浏览器同款 query（web_id 用 __tea__ug__uid 的值）
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
      "input_box_content": {"user_input_content": "本人账号验证：极光下的森林",
                            "reply_message_format": "生成视频：%s"}}
body = json.dumps(build_completion_body(prompt="本人账号验证：极光下的森林",
                                        skill_type=17, ability_param=ap),
                  ensure_ascii=False)
signed = signer.sign(url, body, force=True)
print("minted:", "a_bogus ok" if "a_bogus=" in signed else "MISSING")

verdict, conv = None, ""
with httpx.stream("POST", signed, content=body.encode(),
                  headers={"content-type": "application/json; encoding=utf-8",
                           "cookie": COOKIE, "user-agent":
                           "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"},
                  proxy="http://127.0.0.1:57890", timeout=30) as resp:
    ct = resp.headers.get("content-type", "")
    if "event-stream" not in ct:
        bb = b""
        for c in resp.iter_bytes():
            bb += c
        verdict = f"HTTP {resp.status_code} {bb[:130]}"
    else:
        event = ""
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

if conv:
    from app.upstream.dola.client import DolaClient
    import time
    from app.upstream.dola import parse_chain_response
    from app.upstream.dola.models import TYPE_VIDEO
    cl = DolaClient(COOKIE, device_id="7694970144608241157",
                    web_id="7694973274530743813", proxy="http://127.0.0.1:57890")
    for i in range(40):
        time.sleep(15)
        msgs = parse_chain_response(cl.chain_single_raw(conv))
        vids = [c for m in msgs for c in m.creations if c.type == TYPE_VIDEO]
        if vids and all(v.video.is_finished for v in vids):
            v = vids[0].video
            print(f"✅ GENERATION OK: {v.duration_s}s")
            print("URL:", v.best_url[:160])
            break
        print(f"  poll {i+1}: generating...")
    cl.close()
