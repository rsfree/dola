#!/usr/bin/env python3
"""新号 Tier 1 验证：cookie 存活 + 会话读取。"""
import sys, json
sys.path.insert(0, '/Users/betterme/PycharmProjects/AI/reverse/dola')
from app.upstream.dola import DolaClient

NEW = {
    "new-sv-01": "passport_csrf_token=caaa20ec832198aaa6c88580036e3852;sid_guard=74f27eb5b10aa9c369eac32fc70d12ae%7C1791760057%7C5184000%7CThu%2C+10-Dec-2026+23%3A07%3A37+GMT;uid_tt=3d40e3d3b333e3fe885ed99d839c6ab324b52ea208cbfa4a39e4e454c5b3da9e;sid_tt=74f27eb5b10aa9c369eac32fc70d12ae;sessionid=74f27eb5b10aa9c369eac32fc70d12ae;sessionid_ss=74f27eb5b10aa9c369eac32fc70d12ae;store-idc=mya;store-country-code=sv;ttwid=1%7CrMkVKr_sBMRKwuu5BEj-Oia7e63QwrDZiOuW5jhxBBQ%7C1791760048%7Ce5766883fc9106235520a2e61cd455cf5f27283bb6e855fd608efdfa6d7afc83",
    "new-iq-02": "passport_csrf_token=17df2e1abde66b8281f37755c25e0124;sid_guard=fb054c6fba50537a5f6c4324d06a2dc3%7C1791760065%7C5184000%7CThu%2C+10-Dec-2026+23%3A07%3A45+GMT;uid_tt=0e83e7eaf8e62c69ce48670d9160fbd58dce37f7229579b88c7f9ac5c7adb378;sid_tt=fb054c6fba50537a5f6c4324d06a2dc3;sessionid=fb054c6fba50537a5f6c4324d06a2dc3;sessionid_ss=fb054c6fba50537a5f6c4324d06a2dc3;store-idc=mya;store-country-code=iq;ttwid=1%7C87uamczKkHxN8tPvO4u8FRolJdNNuNtF5hYkz93tUqo%7C1791760059%7Cc7c43e11158f11bbc007b551cab5caed299095e210ce0676c70085680090fbaa",
}

for name, cookie in NEW.items():
    cl = DolaClient(cookie, device_id="7694970144608241157", web_id="7694970157622462005")
    try:
        convs = cl.recent_conv()
        print(f"✅ {name}: ALIVE, {len(convs)} conversations")
    except Exception as e:
        msg = str(e)[:80]
        print(f"❌ {name}: {msg}")
    finally:
        cl.close()
