#!/usr/bin/env python3
"""E2E: 用完整 query 串（18+ 参数）计算 a_bogus。"""
import sys, json, time, urllib.parse
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
from app.upstream.dola.abogus import ABogus
from app.upstream.dola.send_body import build_completion_body
from app.upstream.dola import parse_chain_response
from app.upstream.dola.models import TYPE_IMAGE
from app.nodes import NodeRegistry
from app.accounts import Account
from app.upstream.dola.client import common_query
import httpx

nodes = NodeRegistry('/Users/betterme/PycharmProjects/AI/reverse/dola/data/nodes.local.json')
accounts = {e['name']: e for e in json.load(open('/Users/betterme/PycharmProjects/AI/reverse/dola/data/accounts.local.json'))}
e = accounts['acct-jo-03']
a = Account(name=e['name'], cookie=e['cookie'], node_id=e.get('node'))
cl = a.client(nodes=nodes)

# 完整 query 参数（与浏览器实抓一致）
cq = common_query(device_id='7694970144608241157', web_id='7694970157622462005')
params = dict(cq)
params['region'] = 'TW'
params['sys_region'] = 'TW'
params['pc_version'] = '3.39.1'
params['doubao_pc_version'] = '3.39.1'
params['samantha_web'] = '1'
params['web_platform'] = 'browser'
params['use-olympus-account'] = '1'
params['tz_name'] = 'Asia/Shanghai'
params['web_tab_id'] = 'fd14c83a-f2e9-4d36-9235-403b1493e877'

query_str = '&'.join(f'{k}={v}' for k, v in params.items())
print(f"query params: {len(params)} keys")

PROMPT = "一只企鹅站在冰山上"
body = build_completion_body(prompt=PROMPT, skill_type=3, ability_param={
    "input_box_content": {"user_input_content": PROMPT, "reply_message_format": "生成图片：%s"}})

ab = ABogus()
ab_value = ab.get_value(query_str, method="POST")
full_url = f"{cl._url('/chat/completion')}?{query_str}&a_bogus={urllib.parse.quote(ab_value, safe='')}"

print(f"a_bogus ({len(ab_value)} chars): {ab_value[:60]}...")

conv = ""
with cl.send_completion_signed(full_url, body) as resp:
    for event, data, _ in cl.sse_frames(resp):
        if not data: continue
        if event == "STREAM_ERROR":
            print("ERROR:", data[:250]); break
        if event == "SSE_ACK":
            conv = json.loads(data).get("ack_client_meta",{}).get("conversation_id","")
            print(f"✅ 受理 conv: {conv}")
            break

if conv:
    print("🎉 完整 query + ABogus = 通过！")
    for i in range(40):
        msgs = parse_chain_response(cl.chain_single_raw(conv))
        arts = [c for m in msgs for c in m.creations if c.type == TYPE_IMAGE]
        if arts and all(x.image.is_finished for x in arts):
            img = arts[0].image
            print(f"✅ {len(arts)} 张 {img.width}x{img.height}")
            break
        time.sleep(6)
cl.close()
