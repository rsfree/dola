#!/usr/bin/env python3
"""ByteDance a_bogus 签名算法 —— 纯 Python 实现（SM3 + RC4 + 魔改 Base64）。

基于开源逆向成果（JoeanAmier/TikTokDownloader、DLWangSan/douyin_parse）适配 dola.com。
dola 的 SDK 版本可能不同（webmssdk_1.0.0.44 vs bdms），核心算法族相同但参数需调。
"""
from __future__ import annotations
import json, time, random, struct
from urllib.parse import urlencode, quote
from gmssl import sm3, func

# ---- 字符集（ByteDance 魔改 Base64）----
_CHARSETS = {
    "s0": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=",
    "s1": "Dkdpgh4ZKsQB80/Mfvw36XI1R25+WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=",
    "s2": "Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=",
    "s3": "ckdp1h4ZKsUB80/Mfvw36XIgR25+WQAlEi7NLboqYTOPuzmFjJnryx9HVGDaStCe",
    "s4": "Dkdpgh4ZKsQB80/Mfvw36XI1R25-WUAlEi7NLboqYTOPuzmFjJnryx9HVGcaStCe=",
}

# ---- SM3 初始化向量 ----
_REG_INIT = [0x7380166F, 0x4914B2B9, 0x172442D7, 0xDA8A0600,
             0xA96F30BC, 0x163138AA, 0xE38DEE4D, 0xB0FB0E4E]

_DEFAULT_BROWSER = "1536|742|1536|864|0|0|0|0|1536|864|1536|864|1536|742|24|24|MacIntel"
UA_DEFAULT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")


def _sm3_hash(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return sm3.sm3_hash(func.bytes_to_list(data))


def _rc4(key: bytes, data: bytes) -> bytes:
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) % 256
        S[i], S[j] = S[j], S[i]
    out = bytearray()
    i = j = 0
    for byte in data:
        i = (i + 1) % 256
        j = (j + S[i]) % 256
        S[i], S[j] = S[j], S[i]
        out.append(byte ^ S[(S[i] + S[j]) % 256])
    return bytes(out)


def _b64_encode(data: bytes, charset: str) -> str:
    b64 = ""
    for i in range(0, len(data) - len(data) % 3, 3):
        n = (data[i] << 16) + (data[i+1] << 8) + data[i+2]
        b64 += "".join(charset[(n >> s) & 63] for s in (18, 12, 6, 0))
    rem = len(data) % 3
    if rem == 1:
        n = data[-1] << 16
        b64 += charset[(n >> 18) & 63] + charset[(n >> 12) & 63] + "=="
    elif rem == 2:
        n = (data[-2] << 16) + (data[-1] << 8)
        b64 += "".join(charset[(n >> s) & 63] for s in (18, 12, 6)) + "="
    return b64


def _rc4_encode(text: str, charset: str = "s2") -> str:
    key = b"\x00\x01\x0e"
    encrypted = _rc4(key, text.encode("utf-8"))
    return _b64_encode(encrypted, _CHARSETS[charset])


def _char_code_at(s: str) -> list[int]:
    return [ord(c) for c in s]


class ABogus:
    """生成 ByteDance a_bogus 签名参数（适配 dola.com）。"""

    def __init__(self, user_agent: str = UA_DEFAULT, browser_fp: str = ""):
        self.ua_key = b"\x00\x01\x0e"
        self.ua_code = self._sm3_to_list(_sm3_hash(user_agent))
        self.browser = browser_fp or _DEFAULT_BROWSER
        self.browser_len = len(self.browser)
        self.browser_code = _char_code_at(self.browser)
        self.chunk: list[int] = []
        self.size = 0
        self.reg = _REG_INIT[:]

    @staticmethod
    def _sm3_to_list(hash_hex: str) -> list[int]:
        return [int(hash_hex[i:i+2], 16) for i in range(0, len(hash_hex), 2)][:32]

    @staticmethod
    def _random_list(a=None, b=170, c=85, d=0, e=0, f=0, g=0) -> list[int]:
        r = a or (random.random() * 10000)
        v = [r, int(r) & 255, int(r) >> 8]
        s = v[0] & b | d
        v.append(s)
        s = v[0] & c | e
        v.append(s)
        s = v[0] & b | f
        v.append(s)
        s = v[0] & c | g
        v.append(s)
        return v[-4:]

    def _generate_string_1(self) -> str:
        return "".join(chr(x) for x in self._random_list()) + \
               "".join(chr(x) for x in self._random_list(b=85, c=85, d=0, e=0, f=0)) + \
               "".join(chr(x) for x in self._random_list(b=170, c=85, d=0, e=10, f=0))

    def generate_a_bogus(self, url_query: str, body: str = "",
                         user_agent: str = "") -> str:
        """生成 a_bogus 签名值。

        Args:
            url_query: URL 查询参数字符串（不含 a_bogus 本身）
            body: POST body（如有）
            user_agent: UA 字符串

        Returns:
            a_bogus 签名值
        """
        # 1) SM3 双重哈希
        sm3_url = _sm3_hash(url_query)
        sm3_body = _sm3_hash(body) if body else ""
        sm3_ua = _sm3_hash(user_agent or UA_DEFAULT)

        # 2) RC4 加密 UA
        ua_key = bytes([0x00, 0x01, 0x0E])
        rc4_ua = _rc4(ua_key, (user_agent or UA_DEFAULT).encode())

        # 3) 组装数据包
        timestamp = int(time.time())
        page_id = 26930  # dola pageId
        aid = 495671     # dola aid

        result_list = []
        # 哈希字节
        result_list.extend(self._sm3_to_list(sm3_url)[:16])
        if sm3_body:
            result_list.extend(self._sm3_to_list(sm3_body)[:8])
        # UA 编码
        result_list.extend(list(rc4_ua[:16]))
        # 时间戳（4 字节 big-endian）
        result_list.extend([(timestamp >> s) & 0xFF for s in (24, 16, 8, 0)])
        # aid（4 字节）
        result_list.extend([(aid >> s) & 0xFF for s in (24, 16, 8, 0)])
        # pageId（2 字节）
        result_list.extend([(page_id >> s) & 0xFF for s in (8, 0)])
        # 浏览器指纹长度
        result_list.extend([self.browser_len & 0xFF, (self.browser_len >> 8) & 0xFF])

        # 填充到 4 的倍数
        while len(result_list) % 4 != 0:
            result_list.append(0)

        # 4) 256 数组洗牌
        result_list = self._shuffle_256(result_list)

        # 5) XOR + 随机前缀
        result_list = self._xor_and_prefix(result_list)

        # 6) 魔改 Base64 编码
        raw = bytes(result_list)
        b64_s4 = _b64_encode(raw, _CHARSETS["s4"])
        b64_s2 = _b64_encode(raw, _CHARSETS["s2"])

        return b64_s4

    def _shuffle_256(self, data: list[int]) -> list[int]:
        """256 字节数组洗牌（简化版）。"""
        reg = self.reg[:]
        for i in range(len(data)):
            idx = (data[i] + reg[i % 8]) % 256
            data[i] = (data[i] ^ reg[(i + 3) % 8]) & 0xFF
            reg[idx % 8] = (reg[idx % 8] + data[i]) & 0xFF
        return data

    def _xor_and_prefix(self, data: list[int]) -> list[int]:
        """XOR 操作 + 添加 12 字节随机前缀。"""
        prefix = [random.randint(0, 255) for _ in range(12)]
        result = prefix + data
        # XOR 混淆
        for i in range(len(result)):
            result[i] = (result[i] ^ (i * 7 + 3)) & 0xFF
        return result


if __name__ == "__main__":
    ab = ABogus()
    result = ab.generate_a_bogus("aid=495671&device_platform=web", '{"test":1}')
    print(f"a_bogus length: {len(result)}")
    print(f"a_bogus: {result}")
