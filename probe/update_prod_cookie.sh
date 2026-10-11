#!/bin/bash
# 更新 ai-prod .env 为完整 cookie 并重启
set -e
KEY=~/.ssh/id_ed25519_ops
HOST=root@210.121.44.245
PROJ=/Users/betterme/PycharmProjects/AI/reverse/dola

# 上传完整 cookie 文件
scp -i "$KEY" "$PROJ/probe/.dola_cookie" "$HOST:/opt/dola/ai-prod/dola_cookie_full.txt"

# 在服务器上重建 .env
ssh -i "$KEY" "$HOST" 'cd /opt/dola/ai-prod && echo "DOLA_COOKIE=$(cat dola_cookie_full.txt)" > .env && rm -f dola_cookie_full.txt && docker compose up -d --force-recreate 2>&1 | tail -3'

echo "waiting 20s for signer page..."
sleep 20
ssh -i "$KEY" "$HOST" 'curl -s http://127.0.0.1:39102/healthz && echo && curl -s http://127.0.0.1:39101/healthz'
