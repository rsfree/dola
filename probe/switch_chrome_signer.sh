#!/bin/bash
# 切换到 Chrome signer（node_signer 无法铸签）
set -e
PROJ=/Users/betterme/PycharmProjects/AI/reverse/dola

# 杀掉 node_signer
kill $(lsof -t -i :8491) 2>/dev/null || true
sleep 1

# 启动 Chrome signer
cd "$PROJ"
CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
DOLA_COOKIE="$(cat probe/.dola_cookie)" \
PROXY="http://127.0.0.1:57890" \
PORT=8491 \
nohup "$HOME/.workbuddy/binaries/node/versions/22.22.2-6/bin/node" signer/server.js \
  > /tmp/dola_signer_chrome.log 2>&1 &
echo "chrome signer pid: $!"

# 等待启动 + Chrome 加载页面
echo "waiting 30s for Chrome to load dola page..."
sleep 30

# 验证
HEALTH=$(curl -s --noproxy '*' http://127.0.0.1:8491/healthz --max-time 10 2>/dev/null || echo "DOWN")
echo "chrome signer: $HEALTH"

# 测试铸签
if echo "$HEALTH" | grep -q "page_ready.*true"; then
  echo "✅ signer ready"
elif echo "$HEALTH" | grep -q "page_ready.*false"; then
  echo "⚠️ page not ready yet, waiting 20 more seconds..."
  sleep 20
  HEALTH=$(curl -s --noproxy '*' http://127.0.0.1:8491/healthz --max-time 10 2>/dev/null || echo "DOWN")
  echo "  retry: $HEALTH"
fi
