#!/bin/bash
# 轮询两个新号的任务
KEY=~/.ssh/id_ed25519_ops
HOST=root@210.121.44.245
for i in $(seq 1 20); do
  sleep 30
  A=$(ssh -i "$KEY" "$HOST" "curl -s --max-time 10 http://127.0.0.1:39101/api/v3/contents/generations/tasks/8e7b5b8a08d24664a38ae2026369b93d" 2>/dev/null)
  B=$(ssh -i "$KEY" "$HOST" "curl -s --max-time 10 http://127.0.0.1:39101/api/v3/contents/generations/tasks/8625d58ce00f42c69026aba4bef046c9" 2>/dev/null)
  SA=$(echo "$A" | python3 -c "import json,sys;print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
  SB=$(echo "$B" | python3 -c "import json,sys;print(json.load(sys.stdin).get('status','?'))" 2>/dev/null)
  echo "$((i*30))s: sv-01=$SA | iq-02=$SB"
  if { [ "$SA" = "succeeded" ] || [ "$SA" = "failed" ]; } && { [ "$SB" = "succeeded" ] || [ "$SB" = "failed" ]; }; then
    echo "=== sv-01 ==="; echo "$A" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('FINAL:', d['status'], '| account:', d.get('account'))
if d.get('error'): print('error:', str(d['error'])[:120])
if d.get('content'): print('video_url:', str(d['content'])[:180])
"
    echo "=== iq-02 ==="; echo "$B" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('FINAL:', d['status'], '| account:', d.get('account'))
if d.get('error'): print('error:', str(d['error'])[:120])
if d.get('content'): print('video_url:', str(d['content'])[:180])
"
    break
  fi
done
