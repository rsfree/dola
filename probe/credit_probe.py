#!/usr/bin/env python3
"""零成本账号校验探测：找额度/功能开关查询端点，对比 in-02 vs jo-03。"""
import sys, json
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
import httpx

accounts = json.load(open('/Users/betterme/PycharmProjects/AI/reverse/dola/data/accounts.local.json'))
cookies = {a['name']: a['cookie'] for a in accounts}

CANDIDATES = [
    ("POST", "/alice/commerce/marketing/resource/mget/v2/", {}),
    ("POST", "/alice/commerce/marketing/resource/mget/", {}),
    ("GET",  "/alice/commerce/marketing/card/balance/", None),
    ("POST", "/alice/commerce/marketing/activity/detail/", {}),
]

def probe(name, method, path, body):
    c = httpx.Client(base_url="https://www.dola.com", timeout=15,
                     headers={"content-type": "application/json; encoding=utf-8",
                              "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"})
    cl = cookies[name]
    try:
        if method == "GET":
            r = c.get(path, headers={"cookie": cl})
        else:
            r = c.post(path, content=json.dumps(body), headers={"cookie": cl})
        t = r.text
        return r.status_code, t[:260]
    finally:
        c.close()

for path_note, method, path, body in [("resource/mget/v2", *CANDIDATES[0])]:
    for acct in ["acct-in-02", "acct-jo-03"]:
        code, txt = probe(acct, method, path, body)
        print(f"[{path_note}] {acct}: {code} {txt}\n")
