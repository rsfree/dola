#!/usr/bin/env python3
"""盲扫 prepare_upload 的 resource_type / scene_id，寻找视频/音频上传服务。"""
import sys, json
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
import httpx
from app.nodes import NodeRegistry
from app.upstream.dola.client import UA, common_query, BASE

nodes = NodeRegistry('/Users/betterme/PycharmProjects/AI/reverse/dola/data/nodes.local.json')
proxy = nodes.resolve_proxy(2, "acct-jo-03")
cookie = open('/Users/betterme/PycharmProjects/AI/reverse/dola/probe/.dola_cookie').read().strip()
q = '&'.join(f'{k}={v}' for k, v in common_query(device_id='7694970144608241157',
    web_id='7694970157622462005').items()) + '&region=TW&sys_region=TW&pc_version=3.39.1'

with httpx.Client(trust_env=False, timeout=30, proxy=proxy) as c:
    bh = {'user-agent': UA, 'cookie': cookie, 'origin': BASE,
          'referer': BASE + '/chat/create-video', 'agw-js-conv': 'str',
          'content-type': 'application/json'}
    print("== resource_type sweep (scene_id=4) ==")
    for rt in (0, 1, 2, 3, 4, 5, 6, 7, 10):
        r = c.post(f"{BASE}/alice/resource/prepare_upload?{q}",
                   content=json.dumps({"tenant_id": "5", "scene_id": "4", "resource_type": rt}), headers=bh)
        d = r.json()
        data = d.get('data') or {}
        print(f"  rt={rt}: code={d.get('code')} service={data.get('service_id')} prefix={data.get('upload_path_prefix')}")
    print("== scene_id sweep (resource_type=2) ==")
    for sc in (0, 1, 2, 3, 5, 6, 7):
        r = c.post(f"{BASE}/alice/resource/prepare_upload?{q}",
                   content=json.dumps({"tenant_id": "5", "scene_id": str(sc), "resource_type": 2}), headers=bh)
        d = r.json()
        data = d.get('data') or {}
        print(f"  sc={sc}: code={d.get('code')} service={data.get('service_id')} prefix={data.get('upload_path_prefix')}")
