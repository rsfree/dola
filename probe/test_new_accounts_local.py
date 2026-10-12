#!/usr/bin/env python3
"""新号本地测试：有头真 Chrome 铸签 + 页面真发（最强客户端路径）。"""
import sys, json, urllib.parse
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
import httpx
from app.upstream.dola.send_body import build_completion_body
from app.upstream.dola.signer import SignerClient

signer = SignerClient("http://127.0.0.1:8491", timeout=150)
accounts = json.load(open('/Users/betterme/PycharmProjects/AI/reverse/dola/data/accounts.local.json'))
by_name = {a['name']: a for a in accounts}

def run(name, prompt):
    acct = by_name[name]
    mst = ""
    for part in acct["cookie"].split(";"):
        if part.strip().startswith("msToken="):
            mst = part.strip().split("=", 1)[1]
    Q = ("version_code=20800&language=zh&device_platform=web&doubao_device_platform=web"
         "&fp=verify_mv277m3x_92nktDso_Rc2g_41Ql_8FYI_BcR44nhazpMY"
         "&aid=495671&device_id=7694970144608241157&web_id=7694970157622462005"
         "&doubao_pc_version=3.39.1&pc_version=3.39.1&pkg_type=release_version"
         "&real_aid=495671&region=TW&samantha_web=1&sys_region=TW"
         "&tea_uuid=7694970157622462005&tz_name=Asia%2FShanghai"
         "&use-olympus-account=1&web_platform=browser"
         "&web_tab_id=fd14c83a-f2e9-4d36-9235-403b1493e877")
    if mst:
        Q += f"&msToken={urllib.parse.quote(mst)}"
    url = f"https://www.dola.com/chat/completion?{Q}"

    ap = {"model": "seedance_v2.5", "duration": 10,
          "input_box_content": {"user_input_content": prompt,
                                "reply_message_format": "生成视频：%s"}}
    body = json.dumps(build_completion_body(prompt=prompt, skill_type=17,
                                            ability_param=ap), ensure_ascii=False)
    signed = signer.sign(url, body, force=True)
    ok = "a_bogus ok" if "a_bogus=" in signed else "MISSING"
    r = httpx.post("http://127.0.0.1:8491/send", timeout=90,
                   json={"cookie": acct["cookie"], "url": signed, "body": body})
    head = r.json().get("sse_head", "")
    if "SSE_ACK" in head:
        return f"{name}: 🎉 ACCEPTED"
    for seg in head.split("\n"):
        if "error_code" in seg:
            try:
                d = json.loads(seg.split("data:", 1)[1].strip())
                return f"{name}: {d.get('error_code')} {d.get('error_msg','')[:40]} (mint:{ok})"
            except Exception:
                pass
    return f"{name}: {head[:120]} (mint:{ok})"

print(run("new-sv-01", "新号本地测试：雪山极光"))
print(run("new-iq-02", "新号本地测试：沙漠星空"))
