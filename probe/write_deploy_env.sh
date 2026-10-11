#!/bin/bash
DEPLOY=/Users/betterme/PycharmProjects/AI/reverse/dola/deploy/dola/ai-prod
# signer 不设 PROXY（Seoul 直连 dola.com 可达）；service 的 sticky proxy 由 Bearer 侧决定
printf 'DOLA_COOKIE=%s\n' "$(cat /Users/betterme/PycharmProjects/AI/reverse/dola/probe/.dola_cookie)" > "$DEPLOY/.env"
# gitignore 确认
grep -q '^deploy/' /Users/betterme/PycharmProjects/AI/reverse/dola/.gitignore || echo 'deploy/' >> /Users/betterme/PycharmProjects/AI/reverse/dola/.gitignore
echo "env written"
