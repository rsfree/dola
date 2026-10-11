#!/bin/bash
# 重启 signer → 立即提交视频 → 验证 mssdk 会话新鲜度假设
set -e
KEY=~/.ssh/id_ed25519_ops
HOST=root@210.121.44.245

echo "=== 1. restart signer ==="
ssh -i "$KEY" "$HOST" 'cd /opt/dola/ai-prod && docker compose restart dola-signer' 2>&1 | tail -1
echo "waiting 45s for page + mssdk init..."
sleep 45
ssh -i "$KEY" "$HOST" 'curl -s --max-time 10 http://127.0.0.1:39102/healthz'
echo ""

echo "=== 2. submit immediately ==="
R=$(ssh -i "$KEY" "$HOST" "curl -s --max-time 30 -X POST http://127.0.0.1:39101/api/v3/contents/generations/tasks -H 'Authorization: Bearer bfe8af4095ade8846b0e57edd818cae9' -H 'content-type: application/json' -d '{\"model\":\"doubao-seedance-2-5\",\"content\":[{\"type\":\"text\",\"text\":\"新鲜会话测试\"}],\"duration\":10}'")
echo "$R"
TID=$(echo "$R" | python3 -c "import json,sys;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
echo "task: $TID"

echo "=== 3. poll (45s) ==="
sleep 45
for i in 1 2 3 4 5 6; do
  R=$(ssh -i "$KEY" "$HOST" "curl -s --max-time 10 http://127.0.0.1:39101/api/v3/contents/generations/tasks/$TID" 2>/dev/null)
  ST=$(echo "$R" | python3 -c "import json,sys;print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
  echo "  poll $i: $ST"
  if [ "$ST" = "succeeded" ] || [ "$ST" = "failed" ]; then
    echo "$R" | python3 -c "import json,sys;d=json.load(sys.stdin);print('final:', d['status'], d.get('error','')[:80])"
    break
  fi
  sleep 15
done
