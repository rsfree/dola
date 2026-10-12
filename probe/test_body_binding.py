#!/usr/bin/env python3
"""实验：a_bogus 是否绑定 body？
用 (url, 空body) 铸签，拿去发真实 body + 非法 model。
- shark 若校验 body → 710022004（body 绑定，无法池化预取）
- 若通过 → 走到业务层报参数错 710020202 / 门禁 710020702（URL-only，可池化！）
零消耗：两条路径都不产生生成。
"""
import sys, json
sys.path.insert(0, "/srv")
from app.upstream.dola.send_body import build_completion_body
from app.upstream.dola.client import DolaClient
from app.upstream.dola.signer import SignerClient

signer = SignerClient("http://dola-signer:8491", timeout=150)
accounts = {a["name"]: a for a in json.load(open("/srv/data/accounts.json"))}

acct = accounts["acct-tw-01"]
cl = DolaClient(acct["cookie"], device_id="7694970144608241157",
                web_id="7694970157622462005")

url = cl._url("/chat/completion")

# 1) 用空 body 铸签（预取形态）
sig_url = signer.sign(url, "{}", force=True)
print("minted (empty body):", sig_url[:80], "...a_bogus ok")

# 2) 构造真实 body + 非法 model（必然校验失败，零生成）
ap = {"model": "__probe_invalid__", "duration": 5,
      "input_box_content": {"user_input_content": "probe",
                            "reply_message_format": "生成视频：%s"}}
real_body = build_completion_body(prompt="probe", skill_type=17, ability_param=ap)
real_body_str = json.dumps(real_body, ensure_ascii=False)
print(f"real body len: {len(real_body_str)}")

verdict = None
with cl.send_completion_signed(sig_url, real_body) as resp:
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
                    verdict = data[:80]
                break
            if event == "SSE_ACK":
                verdict = "ACCEPTED(意外)"
                break

cl.close()
print("VERDICT:", verdict)
if verdict and "710022004" in str(verdict):
    print("=> a_bogus 绑定 body，无法预取池")
elif verdict:
    print("=> a_bogus 不含 body（shark 放行到业务层）——可池化预取！")
