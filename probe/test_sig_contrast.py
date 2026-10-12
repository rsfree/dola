#!/usr/bin/env python3
"""对照实验：正确签名 vs 错配签名，同一账号 in-02（已知额度耗尽）。
- 正确 (url, body) 铸签 → 预期 710020702（门禁拒绝）
- 错配 (url, "{}") 铸签 → 此前实测 710022002
两者不同 ⇒ a_bogus 绑定 body（池化预取不可行）。
"""
import sys, json
sys.path.insert(0, "/srv")
from app.upstream.dola.send_body import build_completion_body
from app.upstream.dola.client import DolaClient
from app.upstream.dola.signer import SignerClient

signer = SignerClient("http://dola-signer:8491", timeout=150)
accounts = {a["name"]: a for a in json.load(open("/srv/data/accounts.json"))}
acct = accounts["acct-in-02"]
cl = DolaClient(acct["cookie"], device_id="7694970144608241157",
                web_id="7694970157622462005")
url = cl._url("/chat/completion")

ap = {"model": "__probe_invalid__", "duration": 5,
      "input_box_content": {"user_input_content": "probe",
                            "reply_message_format": "生成视频：%s"}}
real_body = json.dumps(build_completion_body(prompt="probe", skill_type=17,
                                             ability_param=ap), ensure_ascii=False)

def send_with(sig_url, body_str, label):
    verdict = None
    with cl.send_completion_signed(sig_url, body_str) as resp:
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
                    verdict = "ACCEPTED"
                    break
    print(f"{label}: {verdict}")

# A) 正确签名（url + 真实 body）
sig_ok = signer.sign(url, real_body, force=True)
send_with(sig_ok, real_body, "A 正确签名+真实body")

# B) 错配签名（url + 空 body）
sig_wrong = signer.sign(url, "{}", force=True)
send_with(sig_wrong, real_body, "B 错配签名+真实body")

cl.close()
