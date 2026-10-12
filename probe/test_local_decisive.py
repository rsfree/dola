#!/usr/bin/env python3
"""本机决定性对照：家宽 IP + 真 Chrome 铸签 + 新号 sv-01 直发。"""
import sys, json
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
from app.upstream.dola.send_body import build_completion_body
from app.upstream.dola.client import DolaClient
from app.upstream.dola.signer import SignerClient
import time

signer = SignerClient("http://127.0.0.1:8491", timeout=150)
accounts = json.load(open('/Users/betterme/PycharmProjects/AI/reverse/dola/data/accounts.local.json'))
acct = {a['name']: a for a in accounts}['new-sv-01']

# 本机直连（无代理，家宽 IP）
cl = DolaClient(acct['cookie'], device_id="7694970144608241157",
                web_id="7694970157622462005", proxy="http://127.0.0.1:57890")
url = cl._url('/chat/completion')
ap = {"model": "seedance_v2.5", "duration": 10,
      "input_box_content": {"user_input_content": "本机对照：极光雪原",
                            "reply_message_format": "生成视频：%s"}}
body = json.dumps(build_completion_body(prompt="本机对照：极光雪原",
                                        skill_type=17, ability_param=ap),
                  ensure_ascii=False)
signed = signer.sign(url, body, force=True)
print("minted locally:", "a_bogus ok" if "a_bogus=" in signed else "MISSING")

verdict, conv = None, ""
with cl.send_completion_signed(signed, body) as resp:
    if "event-stream" not in resp.headers.get("content-type", ""):
        verdict = f"HTTP {resp.status_code} body={resp.read()[:200]}"
        print("CT:", resp.headers.get("content-type", ""))
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

if conv:
    from app.upstream.dola import parse_chain_response
    from app.upstream.dola.models import TYPE_VIDEO
    for i in range(40):
        time.sleep(15)
        msgs = parse_chain_response(cl.chain_single_raw(conv))
        vids = [c for m in msgs for c in m.creations if c.type == TYPE_VIDEO]
        if vids and all(v.video.is_finished for v in vids):
            v = vids[0].video
            print(f"✅ GENERATION OK: {v.duration_s}s")
            print("URL:", v.best_url[:150])
            break
        print(f"  poll {i+1}: generating...")
cl.close()
