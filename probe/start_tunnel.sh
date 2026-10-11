#!/bin/bash
# SSH 反向隧道：本机 signer(8491) → ai-prod(18491)
# 用 autossh 保持连接
KEY=~/.ssh/id_ed25519_ops
HOST=root@210.121.44.245

# 杀掉已有隧道
pkill -f "ssh.*-R 18491" 2>/dev/null
sleep 1

# 方式1: autossh（自动重连）
if command -v autossh &> /dev/null; then
    autossh -M 0 -f -N \
        -o "ServerAliveInterval=30" \
        -o "ServerAliveCountMax=3" \
        -o "ExitOnForwardFailure=yes" \
        -i "$KEY" -R 18491:127.0.0.1:8491 "$HOST"
    echo "autossh tunnel started"
else
    # 方式2: 普通 ssh 后台
    ssh -f -N \
        -o "ServerAliveInterval=30" \
        -o "ServerAliveCountMax=3" \
        -o "ExitOnForwardFailure=yes" \
        -i "$KEY" -R 18491:127.0.0.1:8491 "$HOST"
    echo "ssh tunnel started"
fi

sleep 2
# 验证：从 ai-prod 侧能否到达
ssh -i "$KEY" "$HOST" 'curl -s http://127.0.0.1:18491/healthz --max-time 5' 2>&1
