#!/usr/bin/env python3
"""在 ai-prod service 容器内跑的零消耗账号判别探测。"""
import sys, json
sys.path.insert(0, "/srv")
from app.upstream.dola.send_body import build_completion_body
from app.upstream.dola.client import DolaClient
from app.upstream.dola.signer import SignerClient

signer = SignerClient("http://dola-signer:8491")
accounts = {a["name"]: a for a in json.load(open("/srv/data/accounts.json"))}

def probe(name):
    acct = accounts[name]
    cl = DolaClient(acct["cookie"], device_id="7694970144608241157",
                    web_id="7694970157622462005")
    ap = {"model": "__probe_invalid__", "duration": 5,
          "input_box_content": {"user_input_content": "probe",
                                "reply_message_format": "生成视频：%s"}}
    body = build_completion_body(prompt="probe", skill_type=17, ability_param=ap)
    url = cl._url("/chat/completion")
    signed_url = signer.sign(url, json.dumps(body, ensure_ascii=False))
    verdict = None
    with cl.send_completion_signed(signed_url, body) as resp:
        if "event-stream" not in resp.headers.get("content-type", ""):
            verdict = f"HTTP {resp.status_code}"
        else:
            for event, data, _ in cl.sse_frames(resp):
                if not data:
                    continue
                if event == "STREAM_ERROR":
                    try:
                        e = json.loads(data)
                        verdict = f"{e.get('error_code')} {e.get('error_msg','')[:40]}"
                    except Exception:
                        verdict = data[:60]
                    break
                if event == "SSE_ACK":
                    verdict = "ACCEPTED(意外)"
                    break
    cl.close()
    print(f"  {name}: {verdict}")

for n in ["acct-in-02", "acct-jo-03", "acct-tw-01"]:
    probe(n)
