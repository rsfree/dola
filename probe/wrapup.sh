#!/bin/bash
# 收尾：同步 compose 回本地 + 提交 + 更新记忆
set -e
KEY=~/.ssh/id_ed25519_ops

scp -i "$KEY" root@210.121.44.245:/opt/dola/ai-prod/docker-compose.yml /Users/betterme/PycharmProjects/AI/reverse/dola/deploy/dola/ai-prod/docker-compose.yml

cd /Users/betterme/PycharmProjects/AI/reverse/dola
git add -A
git commit -m "deploy: SIGNER_TIMEOUT=150s covers self-heal window; canary signer validated" | head -1
git push origin main 2>&1 | tail -1

python3 - <<'PYEOF'
p = '/Users/betterme/PycharmProjects/AI/reverse/dola/.workbuddy/memory/2026-10-11.md'
note = '''
## 10-12 晨补充：模型兜底 + signer 自愈闭环（全部上线）

- **未知模型名兜底**：视频→降级 seedance_v2.5，图像→降级 seedream 4.5，不报错（三个路由全改：video_create / images_sync / images_async）。实测 doubao-seedance-1-5-pro-251215 传入正常排队。
- **signer 金丝雀自愈闭环**：①mintOnce 校验结果含 a_bogus 否则抛错 ②mintSignedUrl 失败→reloadPage ③reloadPage 用金丝雀铸签等 hook 真就绪（15s 轮询上限 8min）④每 4min 后台金丝雀保活（防 ~30min 会话过期）⑤listen-first boot（HTTP 即刻可达）⑥SIGNER_TIMEOUT=150s 覆盖自愈窗口。
- **启发式 hook 检测废弃**：fetch.toString().length>500 在 Docker Chrome 永假，金丝雀是真值。
- mssdk 会话 ~30-40min 过期；自愈一轮 ~2min。剩余 710020702 全为账号问题（额度/信任），工程零遗留。
'''
with open(p, 'a') as f:
    f.write(note)
print('memory updated')
PYEOF
