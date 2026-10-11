#!/usr/bin/env python3
"""E2E: 用纯 Python a_bogus 发 T2I 请求，验证通过 shark 风控。"""
import sys, json, time, uuid, urllib.parse
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
from app.upstream.dola.abogus import ABogus
from app.upstream.dola.send_body import build_completion_body
from app.upstream.dola.client import DolaClient
from app.upstream.dola import parse_chain_response
from app.upstream.dola.models import TYPE_IMAGE
from app.nodes import NodeRegistry
from app.accounts import Account
import httpx

nodes = NodeRegistry('/Users/betterme/PycharmProjects/AI/reverse/dola/data/nodes.local.json')
accounts = {e['name']: e for e in json.load(open('/Users/betterme/PycharmProjects/AI/reverse/dola/data/accounts.local.json'))}
e = accounts['acct-jo-03']
a = Account(name=e['name'], cookie=e['cookie'], node_id=e.get('node'))
cl = a.client(nodes=nodes)

PROMPT = "一只柴犬戴圣诞帽"
ab = ABogus()
body = build_completion_body(prompt=PROMPT, skill_type=3, ability_param={
    "input_box_content": {"user_input_content": PROMPT, "reply_message_format": "生成图片：%s"}, "ratio": "1:1"})
body_str = json.dumps(body, ensure_ascii=False)

query = "aid=495671&device_id=7694970144608241157&device_platform=web&version_code=20800"
ab_value = ab.generate_a_bogus(query, body_str)
signed_url = f"{cl._url('/chat/completion')}&a_bogus={urllib.parse.quote(ab_value)}"
print(f"a_bogus ({len(ab_value)} chars): {ab_value[:60]}...")

conv = ""
with cl.send_completion_signed(signed_url, body) as resp:
    ct = resp.headers.get("content-type","")
    if "event-stream" not in ct:
        print("非SSE:", b"".join(resp.iter_bytes())[:250])
    else:
        for event, data, _ in cl.sse_frames(resp):
            if not data: continue
            if event == "STREAM_ERROR":
                print("STREAM_ERROR:", data[:200]); break
            if event == "SSE_ACK":
                conv = json.loads(data).get("ack_client_meta",{}).get("conversation_id","")
                print("✅ 受理 conv:", conv)
                break

if conv:
    print("🎉 纯 Python a_bogus 通过 shark 风控！")
    for i in range(30):
        msgs = parse_chain_response(cl.chain_single_raw(conv))
        arts = [c for m in msgs for c in m.creations if c.type == TYPE_IMAGE]
        if arts and all(x.image.is_finished for x in arts):
            print(f"✅ {len(arts)} 张图完成")
            break
        hit = [t for m in msgs for t in m.texts if "上限" in t or "额度" in t]
        if hit and not arts:
            print("额度:", hit[0][:50]); break
        time.sleep(6)
cl.close()
