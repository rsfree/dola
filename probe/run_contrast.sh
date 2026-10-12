#!/bin/bash
# 干净重启 signer → 等 canary → 立刻跑对照实验
set -e
KEY=~/.ssh/id_ed25519_ops
HOST=root@210.121.44.245

ssh -i "$KEY" "$HOST" 'cd /opt/dola/ai-prod && docker compose restart dola-signer' 2>&1 | tail -1

echo "waiting for boot canary..."
for i in $(seq 1 20); do
  sleep 30
  L=$(ssh -i "$KEY" "$HOST" 'docker logs ai-prod-dola-signer-1 2>&1 | tail -1' 2>/dev/null)
  if echo "$L" | grep -q "boot canary ok"; then echo "READY after ~$((i*30))s"; break; fi
done

echo "=== contrast experiment (immediately) ==="
ssh -i "$KEY" "$HOST" 'docker exec ai-prod-dola-service-1 python3 /tmp/test_sig_contrast.py'
