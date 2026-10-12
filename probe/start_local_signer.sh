#!/bin/bash
# 本机决定性对照：家宽 IP + 真 Chrome + 新号 sv-01
set -e
PROJ=/Users/betterme/PycharmProjects/AI/reverse/dola

# 1) 清理 8491 并启动本机 Chrome signer（直连，无代理）
kill $(lsof -t -i :8491) 2>/dev/null || true
sleep 1
cd "$PROJ"
CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
DOLA_COOKIE="$(cat probe/.dola_cookie)" \
PORT=8491 \
nohup "$HOME/.workbuddy/binaries/node/versions/22.22.2-6/bin/node" signer/server.js \
  > /tmp/local_signer.log 2>&1 &
echo "local signer pid $!"
for i in $(seq 1 20); do
  sleep 15
  L=$(tail -1 /tmp/local_signer.log)
  echo "  $((i*15))s: $L"
  if echo "$L" | grep -q "boot canary ok"; then echo "READY"; break; fi
done
