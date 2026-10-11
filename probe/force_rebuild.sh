#!/bin/bash
# 强制 rebuild service 容器
set -e
KEY=~/.ssh/id_ed25519_ops
HOST=root@210.121.44.245

# 确认宿主机文件有 fix
echo "=== host file check ==="
ssh -i "$KEY" "$HOST" 'grep -c "get_by_sessionid" /opt/dola/ai-prod/app/main.py'

# 强制 rebuild
echo "=== rebuild ==="
ssh -i "$KEY" "$HOST" 'cd /opt/dola/ai-prod && docker compose build --no-cache dola-service 2>&1 | tail -3'

echo "=== restart ==="
ssh -i "$KEY" "$HOST" 'cd /opt/dola/ai-prod && docker compose up -d dola-service'

sleep 5
echo "=== verify in container ==="
ssh -i "$KEY" "$HOST" 'docker exec ai-prod-dola-service-1 grep -c "get_by_sessionid" /srv/app/main.py'
