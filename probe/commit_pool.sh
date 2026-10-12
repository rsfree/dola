#!/bin/bash
set -e
cd /Users/betterme/PycharmProjects/AI/reverse/dola
git add -A
git commit -m "signer: signature pool (pre-mint, 12ms pooled hits vs 1.5-44s live)

- Experiment: a_bogus binds URL only, NOT body (mismatched sig passed shark,
  reached business-layer validation) => pool pre-minting is viable
- signer: 20s pool filler doubles as hook keepalive; fail-x3 -> self-heal reload
- /sign: pool hit returns in ~12ms with pooled:true flag; live-mint fallback
- POOL_SIZE=12, POOL_TTL=4min (a_bogus TTL >=5min), POOL_URL via env
- corrected: 710020202 = validation-layer error (pre-gate), fires for all
  accounts regardless of quota/trust state" | head -1
git push origin main 2>&1 | tail -1

python3 - <<'PYEOF'
p = '/Users/betterme/PycharmProjects/AI/reverse/dola/.workbuddy/memory/2026-10-11.md'
note = '''
## 10-12 上午：签名池预取（重大突破）

- **🔴 关键实验结论：a_bogus 只绑 URL 不绑 body**——用 (url,"{}") 铸的签名带 2.5KB 不同 body 发送，shark 放行到业务层（710020202 参数错）。错配签名与正确签名同返回码。⇒ 签名可池化预取。
- **修正早前结论**：710020202 是校验层错误（门禁之前），耗尽的 in-02 也返回它 ⇒ Tier-2 探针「invalid-model 判健康」设计无效（所有人都是 202）；710020702 才是门禁真拒绝（需合法参数才触达）。
- **签名池上线**：signer 后台每 20s 补池（POOL_SIZE=12，TTL 4min），/sign URL 严格匹配即秒回（实测 12ms，pooled:true）。filler 兼职 hook 保活，fail x3 自愈 reload。POOL_URL 经 env 注入（compose）。
- **URL 恒定性**：common_query 固定无随机值 ⇒ 单 URL 池覆盖全部请求（所有账号共用同一 device_id/web_id）。
- signer 修复历程：keepalive 10min + fail-twice-then-reload（4min 版 reload 过频反触发会话清除）；listen-first boot（boot canary 60s 就绪）。
- 探针超时之谜：SignerClient 默认 30s timeout 撞上自愈窗口（44s+）——探针脚本需显式 timeout=150。
'''
with open(p, 'a') as f:
    f.write(note)
print('memory updated')
PYEOF
