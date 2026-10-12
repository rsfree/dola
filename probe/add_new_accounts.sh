#!/bin/bash
# 新号入池 + 重启 + 实弹验证
set -e
KEY=~/.ssh/id_ed25519_ops
HOST=root@210.121.44.245
PROJ=/Users/betterme/PycharmProjects/AI/reverse/dola

# 1) 本地把新号合并进 accounts.local.json（幂等）
python3 - <<'PYEOF'
import json
p = '/Users/betterme/PycharmProjects/AI/reverse/dola/data/accounts.local.json'
accounts = [a for a in json.load(open(p)) if a['name'] not in ('new-sv-01', 'new-iq-02')]
sv = "passport_csrf_token=caaa20ec832198aaa6c88580036e3852;sid_guard=74f27eb5b10aa9c369eac32fc70d12ae%7C1791760057%7C5184000%7CThu%2C+10-Dec-2026+23%3A07%3A37+GMT;uid_tt=3d40e3d3b333e3fe885ed99d839c6ab324b52ea208cbfa4a39e4e454c5b3da9e;sid_tt=74f27eb5b10aa9c369eac32fc70d12ae;sessionid=74f27eb5b10aa9c369eac32fc70d12ae;sessionid_ss=74f27eb5b10aa9c369eac32fc70d12ae;store-idc=mya;store-country-code=sv;ttwid=1%7CrMkVKr_sBMRKwuu5BEj-Oia7e63QwrDZiOuW5jhxBBQ%7C1791760048%7Ce5766883fc9106235520a2e61cd455cf5f27283bb6e855fd608efdfa6d7afc83"
iq = "passport_csrf_token=17df2e1abde66b8281f37755c25e0124;sid_guard=fb054c6fba50537a5f6c4324d06a2dc3%7C1791760065%7C5184000%7CThu%2C+10-Dec-2026+23%3A07%3A45+GMT;uid_tt=0e83e7eaf8e62c69ce48670d9160fbd58dce37f7229579b88c7f9ac5c7adb378;sid_tt=fb054c6fba50537a5f6c4324d06a2dc3;sessionid=fb054c6fba50537a5f6c4324d06a2dc3;sessionid_ss=fb054c6fba50537a5f6c4324d06a2dc3;store-idc=mya;store-country-code=iq;ttwid=1%7C87uamczKkHxN8tPvO4u8FRolJdNNuNtF5hYkz93tUqo%7C1791760059%7Cc7c43e11158f11bbc007b551cab5caed299095e210ce0676c70085680090fbaa"
accounts += [
    {"name": "new-sv-01", "cookie": sv, "node": 2},
    {"name": "new-iq-02", "cookie": iq, "node": 2},
]
json.dump(accounts, open(p, 'w'), ensure_ascii=False, indent=1)
print(f"pool: {len(accounts)} accounts:", [a['name'] for a in accounts])
PYEOF

# 2) 上传 + 重启 service
scp -i "$KEY" "$PROJ/data/accounts.local.json" "$HOST:/opt/dola/ai-prod/data/accounts.json" 2>&1 | tail -1
ssh -i "$KEY" "$HOST" 'cd /opt/dola/ai-prod && docker compose restart dola-service' 2>&1 | tail -1
sleep 5

# 3) 实弹验证：两个新号各发一单（10s 视频）
echo "=== submit new-sv-01 ==="
ssh -i "$KEY" "$HOST" "curl -s --max-time 30 -X POST http://127.0.0.1:39101/api/v3/contents/generations/tasks -H 'Authorization: Bearer 74f27eb5b10aa9c369eac32fc70d12ae' -H 'content-type: application/json' -d '{\"model\":\"doubao-seedance-2-5\",\"content\":[{\"type\":\"text\",\"text\":\"sv-01 验证：极光下的雪原\"}],\"duration\":10}'"
echo ""
echo "=== submit new-iq-02 ==="
ssh -i "$KEY" "$HOST" "curl -s --max-time 30 -X POST http://127.0.0.1:39101/api/v3/contents/generations/tasks -H 'Authorization: Bearer fb054c6fba50537a5f6c4324d06a2dc3' -H 'content-type: application/json' -d '{\"model\":\"doubao-seedance-2-5\",\"content\":[{\"type\":\"text\",\"text\":\"iq-02 验证：沙漠日落\"}],\"duration\":10}'"
