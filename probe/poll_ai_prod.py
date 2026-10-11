#!/usr/bin/env python3
"""轮询 ai-prod 上的 Seedance 2.5 30s 视频任务。"""
import sys, json, time, urllib.request
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')

TID = "c75cf73e92304a9c9d7e510699672eef"
BASE = "http://210.121.44.245:39101"
out = '/tmp/ai_prod_25_result.json'

for i in range(240):
    req = urllib.request.Request(f"{BASE}/api/v3/contents/generations/tasks/{TID}")
    resp = urllib.request.urlopen(req, timeout=15)
    d = json.loads(resp.read())
    st = d.get("status")
    if st in ("succeeded", "failed"):
        print(json.dumps(d, ensure_ascii=False, indent=1))
        open(out, 'w').write(json.dumps(d, ensure_ascii=False, indent=1))
        break
    if i % 10 == 0:
        print(f"  {i*10}s status={st}")
    time.sleep(10)
else:
    print("timeout 40min")
    open(out, 'w').write(json.dumps({"status": "timeout"}, ensure_ascii=False))
