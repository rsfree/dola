#!/usr/bin/env python3
"""决定性实验：绕过 registry.pick，直接用 new-sv-01 的完整身份发一次。
身份三件套：自己的 cookie + 自己的粘性代理 IP + 独立 device_id。
"""
import sys, json, hashlib
sys.path.insert(0, "/srv")
from app.upstream.dola.send_body import build_completion_body
from app.upstream.dola.client import DolaClient
from app.upstream.dola.signer import SignerClient

signer = SignerClient("http://dola-signer:8491", timeout=150)
accounts = {a["name"]: a for a in json.load(open("/srv/data/accounts.json"))}

PROXY = "socks5h://poolclient-acct-in-02:Aq68C0iU8x0qFBYP@pool.livetest.cn:2090"
acct = accounts["acct-in-02"]

dev = "7694970144608241157"   # bisect: 用老 device_id
wid = "7694970157622462005"
print(f"identity: sv-01 | device_id={dev} | proxy exit = its own")

cl = DolaClient(acct["cookie"], device_id=dev, web_id=wid, proxy=PROXY)
url = cl._url("/chat/completion")
print("URL:", url[:110], "...")

ap = {"model": "seedance_v2.5", "duration": 10,
      "input_box_content": {"user_input_content": "in-02 对照",
                            "reply_message_format": "生成视频：%s"}}
body = json.dumps(build_completion_body(prompt="in-02 对照",
                                        skill_type=17, ability_param=ap),
                  ensure_ascii=False)
signed = signer.sign(url, body, force=True)
print("signed (fresh):", "a_bogus ok" if "a_bogus=" in signed else "MISSING")

verdict = None
conv = ""
with cl.send_completion_signed(signed, body) as resp:
    if "event-stream" not in resp.headers.get("content-type", ""):
        verdict = f"HTTP {resp.status_code}"
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
    import time
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
        print(f"  poll {i+1}: {len(vids)} vids generating...")
cl.close()
