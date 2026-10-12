#!/bin/bash
# 最终 E2E：未知模型名 → 兜底 2.5 → 铸签 → 上游
KEY=~/.ssh/id_ed25519_ops
HOST=root@210.121.44.245
SID="55dfec296fab7b3a058149ec035e485d"

echo "=== submit (unknown model name) ==="
R=$(ssh -i "$KEY" "$HOST" "curl -s --max-time 30 -X POST http://127.0.0.1:39101/api/v3/contents/generations/tasks -H 'Authorization: Bearer $SID' -H 'content-type: application/json' -d '{\"model\":\"doubao-seedance-1-5-pro-251215\",\"content\":[{\"type\":\"text\",\"text\":\"e2e final: 兜底链路验证\"}],\"duration\":10}'")
echo "$R"
TID=$(echo "$R" | python3 -c "import json,sys;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
[ -z "$TID" ] && exit 1

echo "=== poll every 20s ==="
for i in $(seq 1 15); do
  sleep 20
  R=$(ssh -i "$KEY" "$HOST" "curl -s --max-time 10 http://127.0.0.1:39101/api/v3/contents/generations/tasks/$TID" 2>/dev/null)
  ST=$(echo "$R" | python3 -c "import json,sys;print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
  echo "  $((i*20))s: $ST"
  if [ "$ST" = "succeeded" ] || [ "$ST" = "failed" ]; then
    echo "$R" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('FINAL:', d['status'])
if d.get('error'): print('error:', str(d['error'])[:120])
if d.get('content'): print('video_url:', str(d['content'])[:150])
"
    break
  fi
done
