#!/usr/bin/env python3
"""检查 in-02 的上游视频是否实际生成。"""
import sys, json
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
from app.upstream.dola import DolaClient, parse_chain_response
from app.upstream.dola.models import TYPE_VIDEO

accounts = json.load(open('/Users/betterme/PycharmProjects/AI/reverse/dola/data/accounts.local.json'))
acct = [a for a in accounts if a['name'] == 'acct-in-02'][0]
cl = DolaClient(acct['cookie'], device_id='7694970144608241157', web_id='7694970157622462005')
convs = cl.recent_conv()
newest = convs[0].get('conversation_id')
print(f"newest conv: {newest}")
msgs = parse_chain_response(cl.chain_single_raw(newest))
for m in msgs:
    for c in m.creations:
        if c.type == TYPE_VIDEO:
            v = c.video
            print(f"video: finished={v.is_finished} dur={v.duration_s}s")
            if v.is_finished:
                print(f"URL: {v.best_url[:150]}")
cl.close()
