#!/bin/bash
# 兜底测试：传完全未知的模型名，应降级 2.5 而不是报错
KEY=~/.ssh/id_ed25519_ops
HOST=root@210.121.44.245
SID="55dfec296fab7b3a058149ec035e485d"

echo "=== 1. submit with unknown model name ==="
ssh -i "$KEY" "$HOST" "curl -s --max-time 30 -X POST http://127.0.0.1:39101/api/v3/contents/generations/tasks -H 'Authorization: Bearer $SID' -H 'content-type: application/json' -d '{\"model\":\"doubao-seedance-1-5-pro-251215\",\"content\":[{\"type\":\"text\",\"text\":\"兜底测试：未知模型名应降级\"}],\"duration\":10}'"
echo ""
echo "=== waiting 100s for submit+poll ==="
sleep 100
echo "=== 2. check task status ==="
ssh -i "$KEY" "$HOST" 'docker exec ai-prod-dola-service-1 python3 -c "
import sqlite3
db = sqlite3.connect(\"/srv/data/dola.sqlite3\")
rows = db.execute(\"SELECT model, status, substr(error,1,60) FROM tasks ORDER BY rowid DESC LIMIT 3\").fetchall()
for r in rows: print(r)
"'
