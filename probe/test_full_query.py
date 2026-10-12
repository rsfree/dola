#!/usr/bin/env python3
"""用浏览器完整 query（昨实抓逐字）发 in-02：验证是否缺参导致 710020202。"""
import sys, json
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
from app.upstream.dola.send_body import build_completion_body
from app.upstream.dola.client import DolaClient
from app.upstream.dola.signer import SignerClient

signer = SignerClient("http://127.0.0.1:8491", timeout=150)
accounts = json.load(open('/Users/betterme/PycharmProjects/AI/reverse/dola/data/accounts.local.json'))
acct = {a['name']: a for a in accounts}['new-sv-01']

cl = DolaClient(acct['cookie'], device_id="7694970144608241157",
                web_id="7694970157622462005", proxy="http://127.0.0.1:57890")

# 🔴 昨天实抓的浏览器完整 query（逐字），替换 msToken 为空（cookie 里无）
FULL_QUERY = ("version_code=20800&language=zh&device_platform=web&doubao_device_platform=web"
              "&fp=verify_mv277m3x_92nktDso_Rc2g_41Ql_8FYI_BcR44nhazpMY"
              "&aid=495671&device_id=7694970144608241157&web_id=7694970157622462005"
              "&doubao_pc_version=3.39.1&pc_version=3.39.1&pkg_type=release_version"
              "&real_aid=495671&region=TW&samantha_web=1&sys_region=TW"
              "&tea_uuid=7694970157622462005&tz_name=Asia%2FShanghai"
              "&use-olympus-account=1&web_platform=browser"
              "&web_tab_id=fd14c83a-f2e9-4d36-9235-403b1493e877")
url = f"https://www.dola.com/chat/completion?{FULL_QUERY}"

ap = {"model": "seedance_v2.5", "duration": 10,
      "input_box_content": {"user_input_content": "完整query新号验证",
                            "reply_message_format": "生成视频：%s"}}
body = json.dumps(build_completion_body(prompt="完整query新号验证", skill_type=17,
                                        ability_param=ap), ensure_ascii=False)
signed = signer.sign(url, body, force=True)
print("minted:", "a_bogus ok" if "a_bogus=" in signed else "MISSING")

verdict, conv = None, ""
with cl.send_completion_signed(signed, body) as resp:
    if "event-stream" not in resp.headers.get("content-type", ""):
        verdict = f"HTTP {resp.status_code} {resp.read()[:150]}"
    else:
        for event, data, _ in cl.sse_frames(resp):
            if not data:
                continue
            if event == "STREAM_ERROR":
                try:
                    e = json.loads(data)
                    verdict = f"{e.get('error_code')} {e.get('error_msg','')[:50]}"
                except Exception:
                    verdict = data[:70]
                break
            if event == "SSE_ACK":
                conv = json.loads(data).get("ack_client_meta", {}).get("conversation_id", "")
                verdict = f"ACCEPTED conv={conv}"
                break
print("VERDICT:", verdict)
