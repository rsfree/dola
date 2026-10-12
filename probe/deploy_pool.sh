#!/bin/bash
# 部署签名池 signer：注入 POOL_URL + 重建 + 验证池命中延迟
set -e
KEY=~/.ssh/id_ed25519_ops
HOST=root@210.121.44.245
PROJ=/Users/betterme/PycharmProjects/AI/reverse/dola

POOL_URL='https://www.dola.com/chat/completion?version_code=20800&language=zh&device_platform=web&doubao_device_platform=web&aid=495671&real_aid=495671&pkg_type=release_version&samantha_web=1&web_platform=browser&use-olympus-account=1&device_id=7694970144608241157&web_id=7694970157622462005'

scp -i "$KEY" "$PROJ/signer/server.js" "$HOST:/opt/dola/ai-prod/signer/server.js" 2>&1 | tail -1

# compose 里给 signer 加 POOL_URL（幂等）
ssh -i "$KEY" "$HOST" "cd /opt/dola/ai-prod && \
  grep -q POOL_URL docker-compose.yml || \
  sed -i '/CHROME_PATH=/a\\      - POOL_URL=$POOL_URL' docker-compose.yml; \
  grep -c POOL_URL docker-compose.yml"

ssh -i "$KEY" "$HOST" 'cd /opt/dola/ai-prod && docker compose up -d --build dola-signer' 2>&1 | tail -1
echo "waiting for boot canary..."
for i in $(seq 1 20); do
  sleep 30
  L=$(ssh -i "$KEY" "$HOST" 'docker logs ai-prod-dola-signer-1 2>&1 | tail -1' 2>/dev/null)
  echo "  $((i*30))s: $L"
  if echo "$L" | grep -q "boot canary ok"; then echo "READY"; break; fi
done

echo "=== pool warmup (60s) ==="
sleep 60
echo "=== timed /sign (pool hit should be <100ms) ==="
ssh -i "$KEY" "$HOST" "time curl -s --max-time 30 -X POST http://127.0.0.1:39102/sign -H 'content-type: application/json' -d '{\"url\":\"$POOL_URL\",\"method\":\"POST\",\"body\":\"{}\"}'" 2>&1 | tail -5
