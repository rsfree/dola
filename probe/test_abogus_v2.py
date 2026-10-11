#!/usr/bin/env python3
"""E2E：用完整逆向的 ABogus（168 字符版）发 T2I。"""
import sys, json, time, urllib.parse
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
from app.upstream.dola.abogus import ABogus
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

PROMPT = "一只柴犬在雪地里奔跑，冬日暖阳"
body = build_completion_body(prompt=PROMPT, skill_type=3, ability_param={
    "input_box_content": {"user_input_content": PROMPT, "reply_message_format": "生成图片：%s"}, "ratio": "16:9"})

# 构建 URL 参数（不含 a_bogus）
base_query = "aid=495671&device_platform=web&version_code=20800"
ab = ABogus()
ab_value = ab.get_value(base_query, method="POST")
full_url = f"{cl._url('/chat/completion')}?{base_query}&a_bogus={urllib.parse.quote(ab_value, safe='')}"

print(f"a_bogus ({len(ab_value)} chars): {ab_value[:60]}...")
print(f"URL: ...{full_url[-80:]}")

conv = ""
with cl.send_completion_signed(full_url, body) as resp:
    ct = resp.headers.get("content-type","")
    if "event-stream" not in ct:
        print("非SSE:", b"".join(resp.iter_bytes())[:250])
    else:
        for event, data, _ in cl.sse_frames(resp):
            if not data: continue
            if event == "STREAM_ERROR":
                print("STREAM_ERROR:", data[:250]); break
            if event == "SSE_ACK":
                conv = json.loads(data).get("ack_client_meta",{}).get("conversation_id","")
                print(f"✅ 受理 conv: {conv}")
                break

if conv:
    print("🎉 ABogus v2 通过 shark！")
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
