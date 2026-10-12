#!/bin/bash
# 生产健康 + 池状态 + 真实 E2E
set -e
KEY=~/.ssh/id_ed25519_ops
HOST=root@210.121.44.245

echo "=== 1. containers ==="
ssh -i "$KEY" "$HOST" 'docker compose -f /opt/dola/ai-prod/docker-compose.yml ps --format "table {{.Name}}\t{{.Status}}"'
echo ""
echo "=== 2. signer health + recent logs ==="
ssh -i "$KEY" "$HOST" 'curl -s --max-time 5 http://127.0.0.1:39102/healthz; echo; docker logs ai-prod-dola-signer-1 2>&1 | tail -3'
echo ""
echo "=== 3. pool-hit latency ==="
POOL_URL='https://www.dola.com/chat/completion?version_code=20800&language=zh&device_platform=web&doubao_device_platform=web&aid=495671&real_aid=495671&pkg_type=release_version&samantha_web=1&web_platform=browser&use-olympus-account=1&device_id=7694970144608241157&web_id=7694970157622462005'
ssh -i "$KEY" "$HOST" "curl -s --max-time 30 -X POST http://127.0.0.1:39102/sign -H 'content-type: application/json' -d '{\"url\":\"$POOL_URL\",\"method\":\"POST\",\"body\":\"{}\"}' -o /tmp/pool_hit.json -w '%{http_code} %{time_total}s'; python3 -c \"import json;d=json.load(open('/tmp/pool_hit.json'));print(' pooled:',d.get('pooled'))\""
echo ""
echo "=== 4. real E2E (tw-01 sessionid, unknown model name) ==="
R=$(ssh -i "$KEY" "$HOST" "curl -s --max-time 30 -X POST http://127.0.0.1:39101/api/v3/contents/generations/tasks -H 'Authorization: Bearer 06ec4a34dde002ce98a5558094f0c0fd' -H 'content-type: application/json' -d '{\"model\":\"doubao-seedance-2-5\",\"content\":[{\"type\":\"text\",\"text\":\"清晨薄雾中的江南水乡，乌篷船缓缓驶过石桥\"}],\"duration\":10}'")
echo "$R"
TID=$(echo "$R" | python3 -c "import json,sys;print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
[ -z "$TID" ] && exit 0
echo ""
echo "=== 5. poll ==="
for i in $(seq 1 20); do
  sleep 30
  R=$(ssh -i "$KEY" "$HOST" "curl -s --max-time 10 http://127.0.0.1:39101/api/v3/contents/generations/tasks/$TID" 2>/dev/null)
  ST=$(echo "$R" | python3 -c "import json,sys;print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
  echo "  $((i*30))s: $ST"
  if [ "$ST" = "succeeded" ] || [ "$ST" = "failed" ]; then
    echo "$R" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('FINAL:', d['status'])
if d.get('error'): print('error:', str(d['error'])[:120])
if d.get('content'): print('video_url:', str(d['content'])[:180])
"
    break
  fi
done
