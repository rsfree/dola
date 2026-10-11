#!/bin/bash
# 用 jo-03 的 sessionid 提交
KEY=~/.ssh/id_ed25519_ops
HOST=root@210.121.44.245
PROJ=/Users/betterme/PycharmProjects/AI/reverse/dola

# 提取 jo-03 的 sessionid
JO03_SID=$(python3 -c "
import json
accounts = json.load(open('$PROJ/data/accounts.local.json'))
for a in accounts:
    if a['name'] == 'acct-jo-03':
        # 从 cookie 提取 sessionid
        for part in a['cookie'].split(';'):
            if part.strip().startswith('sessionid='):
                print(part.strip().split('=',1)[1])
                break
        break
")

echo "jo-03 sessionid: ${JO03_SID:0:10}..."

ssh -i "$KEY" "$HOST" "curl -s --max-time 30 -X POST http://127.0.0.1:39101/api/v3/contents/generations/tasks -H 'Authorization: Bearer $JO03_SID' -H 'content-type: application/json' -d '{\"model\":\"dola-seedance-2-5\",\"content\":[{\"type\":\"text\",\"text\":\"雪山之巅日出的史诗场面\"}],\"duration\":30}'"
