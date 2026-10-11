#!/usr/bin/env python3
"""测试：cookie 只透传，完全不带 a_bogus，看能不能过。"""
import sys, json, time
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
from app.upstream.dola.send_body import build_completion_body
from app.upstream.dola import parse_chain_response
from app.upstream.dola.models import TYPE_IMAGE
from app.nodes import NodeRegistry
from app.accounts import Account
import httpx

nodes = NodeRegistry('/Users/betterme/PycharmProjects/AI/reverse/dola/data/nodes.local.json')
accounts = {e['name']: e for e in json.load(open('/Users/betterme/PycharmProjects/AI/reverse/dola/data/accounts.local.json'))}
e = accounts['acct-in-02']
a = Account(name=e['name'], cookie=e['cookie'], node_id=e.get('node'))
cl = a.client(nodes=nodes)

PROMPT = "一只雪豹在雪山之巅，金色日出"
body = build_completion_body(prompt=PROMPT, skill_type=3, ability_param={
    "input_box_content": {"user_input_content": PROMPT, "reply_message_format": "生成图片：%s"}, "ratio": "16:9"})
url = cl._url('/chat/completion')  # 无 a_bogus

conv = ""
with cl.send_completion_signed(url, body) as resp:
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
    print("🎉 无 a_bogus 也通过！")
    for i in range(40):
        msgs = parse_chain_response(cl.chain_single_raw(conv))
        arts = [c for m in msgs for c in m.creations if c.type == TYPE_IMAGE]
        if arts and all(x.image.is_finished for x in arts):
            img = arts[0].image
            print(f"✅ {len(arts)} 张 {img.width}x{img.height}")
            print("URL:", img.raw_url[:110])
            break
        hit = [t for m in msgs for t in m.texts if "上限" in t or "额度" in t]
        if hit and not arts:
            print("额度:", hit[0][:50]); break
        time.sleep(6)
cl.close()
