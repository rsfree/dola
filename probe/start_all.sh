#!/bin/bash
# 一键启动：本地 signer + SSH 隧道
set -e
PROJ=/Users/betterme/PycharmProjects/AI/reverse/dola
KEY=~/.ssh/id_ed25519_ops
HOST=root@210.121.44.245

# 1) 本地 signer
echo "=== 1. local signer ==="
curl -s --noproxy '*' http://127.0.0.1:8491/healthz --max-time 5 2>/dev/null && echo " already running" || {
  echo " starting..."
  export CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  export DOLA_COOKIE="$(cat $PROJ/probe/.dola_cookie)"
  export PROXY="http://127.0.0.1:57890"
  export PORT=8491
  nohup $HOME/.workbuddy/binaries/node/versions/22.22.2-6/bin/node $PROJ/signer/server.js > /tmp/dola_signer.log 2>&1 &
  echo $! > /tmp/dola_signer.pid
  sleep 20
}
HEALTH=$(curl -s --noproxy '*' http://127.0.0.1:8491/healthz --max-time 5 2>/dev/null || echo "DOWN")
echo "  local signer: $HEALTH"

# 2) SSH 隧道
echo "=== 2. SSH tunnel ==="
pkill -f "ssh.*-R 18491" 2>/dev/null || true
sleep 1
ssh -f -N \
    -o "ServerAliveInterval=30" \
    -o "ServerAliveCountMax=3" \
    -o "ExitOnForwardFailure=yes" \
    -o "StrictHostKeyChecking=no" \
    -i "$KEY" -R 18491:127.0.0.1:8491 "$HOST" 2>/dev/null
echo "  tunnel: local:8491 → ai-prod:18491"
sleep 2

# 3) 验证从 ai-prod 侧
echo "=== 3. verify from ai-prod ==="
REMOTE=$(ssh -i "$KEY" "$HOST" 'curl -s http://127.0.0.1:18491/healthz --max-time 5' 2>/dev/null || echo "unreachable")
echo "  ai-prod → tunnel → signer: $REMOTE"
