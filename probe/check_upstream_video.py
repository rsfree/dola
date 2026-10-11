#!/usr/bin/env python3
"""检查上游视频是否实际生成 + 加大 ai-prod 轮询超时。"""
import subprocess, json

KEY = "~/.ssh/id_ed25519_ops"
HOST = "root@210.121.44.245"

# 检查上游
check_script = '''
import sys, json; sys.path.insert(0,"/srv")
from app.upstream.dola import DolaClient, parse_chain_response
from app.upstream.dola.models import TYPE_VIDEO
accounts = json.load(open("/srv/data/accounts.json"))
acct = [a for a in accounts if a["name"]=="acct-in-02"][0]
cl = DolaClient(acct["cookie"], device_id="7694970144608241157", web_id="7694970157622462005")
convs = cl.recent_conv()
newest = convs[0].get("conversation_id")
print(f"newest conv: {newest}")
msgs = parse_chain_response(cl.chain_single_raw(newest))
for m in msgs:
    for c in m.creations:
        if c.type == TYPE_VIDEO:
            v = c.video
            print(f"video: finished={v.is_finished} dur={v.duration_s}s")
            if v.is_finished:
                print(f"URL: {v.best_url[:120]}")
cl.close()
'''
r = subprocess.run(["ssh", "-i", KEY.replace("~", "/Users/betterme"), HOST,
                    f'docker exec ai-prod-dola-service-1 python3 -c \'{check_script}\''],
                   capture_output=True, text=True, timeout=30)
print("=== upstream check ===")
print(r.stdout or r.stderr)
