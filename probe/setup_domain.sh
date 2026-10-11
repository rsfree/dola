#!/bin/bash
# dola.1task.cn: nginx vhost + DNS A 记录
set -e
KEY=~/.ssh/id_ed25519_ops
HOST=root@210.121.44.245
PROJ=/Users/betterme/PycharmProjects/AI/reverse/dola

echo "=== 1. nginx vhost (:80) ==="
ssh -i "$KEY" "$HOST" 'cat > /www/server/panel/vhost/nginx/dola.1task.cn.conf << "NGINX"
server {
    listen 80;
    server_name dola.1task.cn;

    location ^~ /.well-known/acme-challenge/ {
        root /www/wwwroot/dola.1task.cn;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}
NGINX
mkdir -p /www/wwwroot/dola.1task.cn
/www/server/nginx/sbin/nginx -t 2>&1'
echo ""

echo "=== 2. reload nginx ==="
ssh -i "$KEY" "$HOST" '/www/server/nginx/sbin/nginx -s reload && echo "nginx reloaded"'
sleep 2
echo ""

echo "=== 3. DNS A record ==="
python3 - <<'PYEOF'
import json, os, sys
sys.path.insert(0, os.path.expanduser("~/.workbuddy/binaries/python/envs/default/lib/python3.13/site-packages"))
from aliyunsdkcore.client import AcsClient
from aliyunsdkalidns.request.v20150109.DescribeDomainRecordsRequest import DescribeDomainRecordsRequest
from aliyunsdkalidns.request.v20150109.AddDomainRecordRequest import AddDomainRecordRequest

cfg = json.load(open(os.path.expanduser("~/.aliyun/config.json")))
prof = next(p for p in cfg["profiles"] if p["name"] == cfg.get("current", "default"))
client = AcsClient(prof["access_key_id"], prof["access_key_secret"], prof.get("region_id"))

# 幂等检查
req = DescribeDomainRecordsRequest()
req.set_DomainName("1task.cn")
req.set_RRKeyWord("dola")
resp = client.do_action_with_exception(req)
records = json.loads(resp)["DomainRecords"]["Record"]
existing = [r for r in records if r["RR"] == "dola"]
if existing:
    print(f"DNS already exists: {existing[0]['Value']}")
else:
    add = AddDomainRecordRequest()
    add.set_DomainName("1task.cn")
    add.set_RR("dola")
    add.set_Type("A")
    add.set_Value("210.121.44.245")
    add.set_TTL(600)
    resp = client.do_action_with_exception(add)
    print(f"DNS added: {json.loads(resp)['RecordId']}")
PYEOF
echo ""

echo "=== 4. verify DNS + nginx ==="
sleep 3
ssh -i "$KEY" "$HOST" 'curl -s -o /dev/null -w "%{http_code}" --resolve dola.1task.cn:80:127.0.0.1 http://dola.1task.cn/healthz'
echo " (nginx :80 → 301 expected)"
# 权威 NS 验证
nslookup dola.1task.cn dns13.hichina.com 2>/dev/null | /usr/bin/grep "Address" | tail -1
