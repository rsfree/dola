#!/usr/bin/env python3
"""测 u8dpqn1f20 服务（resource_type=1）收不收 mp4：prepare → apply(mp4) → commit。"""
import sys, json, os, hashlib, hmac, zlib, urllib.parse
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
import httpx
from app.nodes import NodeRegistry
from app.upstream.dola.client import UA, common_query, BASE
import datetime as dt

MP4 = open('/tmp/test_ref.mp4', 'rb').read()

def _sha(b): return hashlib.sha256(b).hexdigest()
def _hmac(k, m): return hmac.new(k, m.encode(), hashlib.sha256).digest()
def _uri(s): return urllib.parse.quote(s, safe="-_.~")

def aws4_sign(method, host, path, query, ak, sk, token, payload, region, service):
    now = dt.datetime.now(dt.timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ"); date = now.strftime("%Y%m%d")
    hdrs = {"host": host, "x-amz-date": amz_date, "x-amz-security-token": token,
            "x-amz-content-sha256": _sha(payload)}
    signed = "x-amz-content-sha256;x-amz-date;x-amz-security-token"
    cq = "&".join(f"{_uri(k)}={_uri(v)}" for k, v in sorted(query.items()))
    ch = "".join(f"{h}:{hdrs[h]}\n" for h in signed.split(";"))
    creq = "\n".join([method, path, cq, ch, signed, _sha(payload)])
    scope = f"{date}/{region}/{service}/aws4_request"
    sts = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, _sha(creq.encode())])
    k = _hmac(("AWS4"+sk).encode(), date); k = _hmac(k, region); k = _hmac(k, service); k = _hmac(k, "aws4_request")
    sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()
    return {"x-amz-date": amz_date, "x-amz-security-token": token,
            "x-amz-content-sha256": _sha(payload),
            "content-type": "application/json",
            "authorization": f"AWS4-HMAC-SHA256 Credential={ak}/{scope}, SignedHeaders={signed}, Signature={sig}"}

nodes = NodeRegistry('/Users/betterme/PycharmProjects/AI/reverse/dola/data/nodes.local.json')
proxy = nodes.resolve_proxy(2, "acct-jo-03")
cookie = open('/Users/betterme/PycharmProjects/AI/reverse/dola/probe/.dola_cookie').read().strip()
UID = "7694968299444028469"
q = '&'.join(f'{k}={v}' for k, v in common_query(device_id='7694970144608241157',
    web_id='7694970157622462005').items()) + '&region=TW&sys_region=TW&pc_version=3.39.1'

with httpx.Client(trust_env=False, timeout=60, proxy=proxy) as c:
    bh = {'user-agent': UA, 'cookie': cookie, 'origin': BASE,
          'referer': BASE + '/chat/create-video', 'agw-js-conv': 'str',
          'content-type': 'application/json'}
    r = c.post(f"{BASE}/alice/resource/prepare_upload?{q}",
               content='{"tenant_id":"5","scene_id":"4","resource_type":1}', headers=bh)
    prep = r.json()['data']
    tok = prep['upload_auth_token']
    print("service:", prep['service_id'], "prefix:", prep['upload_path_prefix'])
    host = prep['upload_host'].replace('https://', '')
    query = {"Action": "ApplyImageUpload", "Version": "2018-08-01",
             "ServiceId": prep['service_id'], "FileSize": str(len(MP4)),
             "FileExtension": ".mp4", "s": "xb7g04218ho"}
    ah = aws4_sign("GET", host, "/", query, tok['access_key'], tok['secret_key'],
                   tok['session_token'], b"", "us-east-1", "imagex")
    r = c.get(f"https://{host}/?{urllib.parse.urlencode(query)}", headers={**ah, "user-agent": UA})
    print("Apply(mp4):", r.status_code)
    if 'StoreInfos' not in r.text:
        print(r.text[:250]); sys.exit(1)
    d = r.json()['Result']['UploadAddress']
    store = d['StoreInfos'][0]
    uh = d['UploadHosts'][0] if isinstance(d.get('UploadHosts'), list) else d.get('UploadHosts')
    sk = d['SessionKey']
    crc = format(zlib.crc32(MP4) & 0xffffffff, '08x')
    bh2 = {"Authorization": store['Auth'], "X-Storage-U": UID,
           "Origin": "https://www.dola.com", "Referer": "https://www.dola.com/", "user-agent": UA}
    r = c.post(f"https://{uh}/upload/v1/{store['StoreUri']}?uploadmode=part&phase=init",
               headers={**bh2, "Content-Type": "multipart/form-data; boundary=----x"},
               content=b"------x--\r\n")
    uid2 = json.loads(r.text)['data']['uploadid']
    r = c.post(f"https://{uh}/upload/v1/{store['StoreUri']}?uploadid={uid2}&part_number=1&phase=transfer",
               headers={**bh2, "Content-CRC32": crc,
                        "Content-Disposition": 'attachment; filename="undefined"',
                        "Content-Type": "application/octet-stream"}, content=MP4)
    print("transfer:", r.status_code, r.text[:100])
    r = c.post(f"https://{uh}/upload/v1/{store['StoreUri']}?uploadmode=part&phase=finish&uploadid={uid2}",
               headers={**bh2, "Content-Type": "text/plain;charset=UTF-8"}, content=f"1:{crc}")
    print("finish:", r.status_code, r.text[:120])
    q2 = {"Action": "CommitImageUpload", "Version": "2018-08-01", "ServiceId": prep['service_id']}
    ah = aws4_sign("POST", host, "/", q2, tok['access_key'], tok['secret_key'], tok['session_token'],
                   json.dumps({"SessionKey": sk}).encode(), "us-east-1", "imagex")
    r = c.post(f"https://{host}/?{urllib.parse.urlencode(q2)}",
               content=json.dumps({"SessionKey": sk}).encode(), headers={**ah, "user-agent": UA})
    res = r.json()['Result']['Results'][0]
    print(f"✓ Commit: uri={res['Uri']} status={res['UriStatus']}")
    if res.get('ImageWidth'):
        print(f"  元数据: {res['ImageWidth']}x{res['ImageHeight']} {res.get('ImageFormat')} {res.get('ImageSize')}B")
    open('/tmp/mp4_commit.json', 'w').write(json.dumps(r.json(), ensure_ascii=False, indent=1))
