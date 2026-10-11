#!/bin/bash
# 部署账号池到 ai-prod + 配置 DOLA_ACCOUNTS_FILE
set -e
KEY=~/.ssh/id_ed25519_ops
HOST=root@210.121.44.245
PROJ=/Users/betterme/PycharmProjects/AI/reverse/dola

# 上传账号池和节点配置
scp -i "$KEY" "$PROJ/data/accounts.local.json" "$HOST:/opt/dola/ai-prod/data/accounts.json"
scp -i "$KEY" "$PROJ/data/nodes.local.json" "$HOST:/opt/dola/ai-prod/data/nodes.json"

# 更新 docker-compose.yml 加 DOLA_ACCOUNTS_FILE
ssh -i "$KEY" "$HOST" 'cd /opt/dola/ai-prod && \
  sed -i "/DB_PATH/a\      - DOLA_ACCOUNTS_FILE=/srv/data/accounts.json\n      - DOLA_NODES_FILE=/srv/data/nodes.json" docker-compose.yml && \
  grep -A5 "DOLA_COOKIE" docker-compose.yml | head -8'

# 重启
ssh -i "$KEY" "$HOST" 'cd /opt/dola/ai-prod && docker compose up -d --force-recreate dola-service' 2>&1 | tail -1
sleep 5

# 验证
ssh -i "$KEY" "$HOST" 'curl -s http://127.0.0.1:39101/healthz && echo && curl -s http://127.0.0.1:39101/v1/accounts 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);print(f\"accounts: {len(d)} loaded\")" 2>/dev/null || echo "accounts endpoint not available"'
