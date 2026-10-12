#!/usr/bin/env python3
"""msToken 假设验证：从 signer 页面取活 msToken → 拼进 query → 铸签 → 发送。"""
import sys, json, urllib.parse
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
import httpx
from app.upstream.dola.send_body import build_completion_body
from app.upstream.dola.client import DolaClient
from app.upstream.dola.signer import SignerClient

signer = SignerClient("http://127.0.0.1:8491", timeout=150)

# 1) 从 signer 页面取 msToken（加个临时端点？不，直接用 healthz 之外的方式——
#    signer 没有该端点，改为从 cookie 接口……signer 没有暴露。改从本地 Chrome 的
#    dola cookie 拿——直接让 signer 出一个页面 cookie 需要加代码。
#    → 快速路径：直接请求 dola.com 首页拿 Set-Cookie 里的 msToken？msToken 由 JS 设置。
#    → 最快：signer.sign 的是 URL；我们另开一个端点不值得，先手动从页面 evaluate。
#    这里改用 node 一行拿（signer 进程内的 page 对象不可外部访问）……
#    简化：用 httpx 直接访问 dola.com 某页面，msToken 常由 mssdk JS 写入，纯 HTTP 拿不到。
#    ⇒ 先测「无 msToken 但带 region 等全部参数 + 2.5 body + 新号 + 本机」基线已经 202。
#    ⇒ 本脚本改为：从 signer 的 Chrome 里读 cookie —— 通过 CDP HTTP 接口（signer 启动
#       时 puppeteer 默认开 DevTools 端口？未开。）
# 结论：先快速给 signer 加 /pageinfo 端点输出 msToken，再跑。
print("需要 signer 暴露 msToken —— 见 add_msToken_endpoint.py")
