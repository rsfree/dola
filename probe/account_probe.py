#!/usr/bin/env python3
"""零额度判别实验：非法 ability_param.model 的 send 探测。
错误码语义：710020202=参数校验(说明过了门禁) / 710020702=门禁拒绝 / 710012001=cookie 失效
"""
import sys, json
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
from app.upstream.dola.send_body import build_completion_body
from app.upstream.dola.client import DolaClient
from app.upstream.dola import parse_chain_response

accounts = {a['name']: a for a in json.load(open('/Users/betterme/PycharmProjects/AI/reverse/dola/data/accounts.local.json'))}

def probe(name):
    acct = accounts[name]
    cl = DolaClient(acct['cookie'], device_id='7694970144608241157', web_id='7694970157622462005')
    # 非法 model 值 → 若上游先做参数校验，会返回 param invalid（不耗额度）
    ap = {"model": "__probe_invalid__", "duration": 5,
          "input_box_content": {"user_input_content": "probe", "reply_message_format": "生成视频：%s"}}
    body = build_completion_body(prompt="probe", skill_type=17, ability_param=ap)
    url = cl._url('/chat/completion')
    verdict = None
    with cl.send_completion_signed(url, body) as resp:
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
                    verdict = "ACCEPTED (!!) 意外受理"
                    break
    cl.close()
    print(f"  {name}: {verdict}")
    return verdict

print("=== 非法 model 探测（零消耗预期）===")
probe("acct-in-02")   # 今天已耗尽（生成了 2 个视频）→ 预期 710020702
probe("acct-jo-03")   # 信任门控 → 预期 710020702
probe("acct-tw-01")   # 昨天耗尽，今天可能已重置 → 若 202 = 健康
