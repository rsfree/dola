#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dola (dola.com) 上游客户端 —— 读侧（消息链）纯 HTTP；写侧（生成）契约构建。

上游契约见 `docs/upstream/dola-api.md`。本模块只做「翻译 + 信封 + 错误分类」。

## 已实证的分层（2026-10-10 负对照，probe/negctl/）

| 请求形态 | 结果 | 判定 |
|---|---|---|
| `/im/chain/single` content-type=`application/json`（无 `encoding=utf-8`） | `712012002 不支持编码类型` | 信封层在鉴权**之前** |
| 同上，content-type=`application/json; encoding=utf-8`，无 cookie | `712012001 登录校验不合法` | 鉴权层；**无签名报错** |
| `POST /chat/completion` 无 cookie 无 msToken/a_bogus | SSE 打开 → `STREAM_ERROR 710012001 login invalid` | 🔴 **网关不强制 a_bogus**（写侧同判） |
| `GET /chat/completion` | 404 | POST-only |

⇒ **纯 HTTP + cookie 即可走通读写**（a_bogus 未被网关强制；字节风控可能动态开启，
   参考 jimeng `1014 ErrSign` 的先例 —— 上线后要盯着）。

## 最小凭据

cookie 字符串（浏览器"复制全部 cookie"即可，尚未做最小集负对照 —— ❓）。
`DolaAuthError` 出现 ⇒ cookie 过期/缺失，唯一动作是换新。

## 🔴 计费纪律

`send_completion()` 是**计费动作**（图像 1x/4x，视频 2 额度起）。
默认 `dry_run=True` 只构建请求体**不发请求**；真发必须显式 `dry_run=False`
且调用方已向用户确认过消耗。
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from .models import Creation, MessageBlocks, parse_chain_response

BASE = "https://www.dola.com"

PATH_RECENT_CONV = "/im/chain/recent_conv"
PATH_CHAIN_SINGLE = "/im/chain/single"
PATH_CONV_BATCH_GET = "/im/conversation/batch_get"
PATH_SEND_RATE_LIMIT = "/im/message/send_rate_limit"
PATH_COMPLETION = "/chat/completion"
PATH_ASYNC_STREAM = "/chat/async/chunk_stream"

#: BFF 信封 cmd（实抓）
CMD_CHAIN_SINGLE = 3100
CMD_RECENT_CONV = 3200
CMD_RATE_LIMIT = 2260

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

#: AGW 信封层的错误码（负对照实抓）
CODE_AUTH = 712012001           # 登录校验不合法
CODE_ENCODING = 712012002       # 不支持编码类型
#: SSE 流内的错误码（/chat/completion 实抓）
SSE_CODE_AUTH = 710012001       # login invalid


class DolaError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None,
                 status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class DolaAuthError(DolaError):
    """cookie 缺失/过期。唯一动作：换新凭据。"""


class DolaEnvelopeError(DolaError):
    """信封/编码被拒（content-type 错、body 非法）。"""


def classify_status_code(code: int | None) -> tuple[str, bool]:
    """AGW `status_code` → (类别, 是否可重试)。新码见到再补表。"""
    if code == 0:
        return "ok", False
    if code == CODE_AUTH:
        return "auth", False
    if code == CODE_ENCODING:
        return "envelope", False
    return "unknown", True


def common_query(*, device_id: str = "", web_id: str = "",
                 extra: dict[str, str] | None = None) -> dict[str, str]:
    """公共 query。浏览器抓包逐字对齐（版本号会随发版漂移，出 712012002 时先查这里）。"""
    q = {
        "version_code": "20800",
        "language": "zh",
        "device_platform": "web",
        "doubao_device_platform": "web",
        "aid": "495671",
        "real_aid": "495671",
        "pkg_type": "release_version",
        "samantha_web": "1",
        "web_platform": "browser",
        "use-olympus-account": "1",
    }
    if device_id:
        q["device_id"] = device_id
    if web_id:
        q["web_id"] = web_id
    if extra:
        q.update(extra)
    return q


def envelope(cmd: int, uplink_body: dict) -> dict:
    """BFF 信封。`sequence_id` 客户端自生成（uuid4）—— 回执原样带回，可自校验。"""
    return {
        "cmd": cmd,
        "uplink_body": uplink_body,
        "sequence_id": str(uuid.uuid4()),
        "channel": 2,
        "version": "1",
    }


def chain_single_body(conversation_id: str, *, limit: int = 20) -> dict:
    return envelope(CMD_CHAIN_SINGLE, {
        "pull_singe_chain_uplink_body": {
            "conversation_id": str(conversation_id),
            "anchor_index": 9007199254740991,   # 浏览器实抓值 = 2^53-1（取最新）
            "conversation_type": 3,
            "direction": 1,
            "limit": limit,
            "ext": {},
            "filter": {"index_list": []},
            "evaluate_ab_params": "",
            "evaluate_common_params": "",
            "option": {"lazy_load_strategy": 0},
        },
    })


from .send_body import (SKILL_IMAGE, SKILL_VIDEO, build_completion_body)  # 实抓版见 send_body.py


class DolaClient:
    """读侧客户端。`cookie` 是原始 Cookie 头字符串（`a=1; b=2` 或分号换行混合）。"""

    def __init__(self, cookie: str, *, device_id: str = "", web_id: str = "",
                 timeout: float = 15.0, proxy: str | None = None) -> None:
        self.cookie = self._normalize_cookie(cookie)
        self.device_id = device_id
        self.web_id = web_id
        self._http = httpx.Client(
            timeout=timeout,
            trust_env=False,   # 🔴 环境代理会吞带凭据的请求（用户纪律）
            # 🔴 dola 写侧有地理围栏（710022003 country restricted，实抓）：
            #    国内直连被拒、读侧不拦。浏览器能生成 = 走了系统代理。
            #    部署在国内时写路径必须显式传 proxy（如 http://127.0.0.1:57890）。
            proxy=proxy,
            headers={
                "user-agent": UA,
                "cookie": self.cookie,
                "origin": BASE,
                "agw-js-conv": "str",
                "accept": "application/json, text/plain, */*",
            },
        )

    @staticmethod
    def _normalize_cookie(raw: str) -> str:
        raw = raw.strip()
        if "\n" in raw:
            # 每行一个 a=1 的写法 → 一行
            lines = [ln.strip().rstrip(";") for ln in raw.splitlines() if ln.strip()]
            return "; ".join(lines)
        return raw

    def _url(self, path: str) -> str:
        q = common_query(device_id=self.device_id, web_id=self.web_id)
        return f"{BASE}{path}?{ '&'.join(f'{k}={v}' for k, v in q.items()) }"

    def _post_bff(self, path: str, body: dict) -> dict:
        """BFF 信封 POST。信封错误码在 `status_code` 字段（HTTP 恒 200）。"""
        # 🔴 content-type 的 `encoding=utf-8` 不是装饰 —— 少了它 712012002（负对照 N1）。
        r = self._http.post(self._url(path),
                            content=json.dumps(body, ensure_ascii=False),
                            headers={"content-type": "application/json; encoding=utf-8",
                                     "referer": BASE + "/"})
        r.raise_for_status()
        data = r.json()
        code = data.get("status_code")
        kind, retryable = classify_status_code(code)
        if kind == "auth":
            raise DolaAuthError(f"登录校验失败 status_code={code} {data.get('status_desc')}",
                                code=code)
        if kind == "envelope":
            raise DolaEnvelopeError(f"信封被拒 status_code={code} {data.get('status_desc')}",
                                    code=code)
        if code not in (0, None) and kind == "unknown":
            raise DolaError(f"上游错误 status_code={code} {data.get('status_desc')}",
                            status_code=code)
        return data.get("downlink_body") or {}

    # ---- 读侧 ----

    def recent_conv(self, *, limit: int = 50) -> list[dict]:
        """会话列表（cells[].conversation）。

        body 逐字对齐浏览器实抓（2026-10-10）：字段名是 `conv_version`（不是
        anchor_index），`direction=3`，`option` 里一组开关；缺它们 ⇒ 200 但
        `cells=[]` 静默空列表（本客户端踩过的坑）。
        """
        body = envelope(CMD_RECENT_CONV, {
            "pull_recent_conv_chain_uplink_body": {
                "limit": limit,
                "filter": {"conversation_type": [], "project_filter": 1},
                "message_count_per_conv": 0,
                "api_version": 1,
                "conv_version": 0,
                "direction": 3,
                "option": {
                    "not_need_message": True,
                    "need_complete_conversation": True,
                    "need_coco_bot": True,
                    "need_pc_pin_chain": True,
                    "pc_pin_query_type": 1,
                    "exclude_archive": True,
                    "only_archive": False,
                },
            },
        })
        db = self._post_bff(PATH_RECENT_CONV, body)
        pull = (db.get("pull_recent_conv_chain_downlink_body") or {})
        return [c.get("conversation") or {} for c in (pull.get("cells") or [])
                if isinstance(c, dict)]

    def chain_single(self, conversation_id: str, *, limit: int = 20) -> list[MessageBlocks]:
        """单会话消息链 → 解析后的消息块。"""
        db = self._post_bff(PATH_CHAIN_SINGLE, chain_single_body(conversation_id, limit=limit))
        return parse_chain_response(db)

    def chain_single_raw(self, conversation_id: str, *, limit: int = 20) -> dict:
        return self._post_bff(PATH_CHAIN_SINGLE,
                              chain_single_body(conversation_id, limit=limit))

    # ---- 写侧 ----

    def send_completion(self, body: dict, *, dry_run: bool = True) -> httpx.Response:
        """发送生成。🔴 计费动作。默认 dry_run 只回显将发送的请求。"""
        if dry_run:
            raise DolaError("dry_run=True：已阻止发送（计费动作需显式 dry_run=False）")
        url = self._url(PATH_COMPLETION)
        # 浏览器实抓：无 msToken/a_bogus 也能到达业务层（网关不强制，2026-10-10）
        return self._http.stream("POST", url,
                                 content=json.dumps(body, ensure_ascii=False),
                                 headers={"content-type": "application/json; encoding=utf-8",
                                          "referer": BASE + "/chat/create-image",
                                          "accept": "text/event-stream"})

    def send_completion_signed(self, signed_url: str, body: dict) -> httpx.Response:
        """用铸签 URL 发送（过 shark 风控的唯一姿势，docs §4.0.1）。

        signed_url 由铸签 sidecar 产出（含 msToken+a_bogus）；body 必须与铸签时
        **逐字节一致**（a_bogus 覆盖 body）。
        """
        return self._http.stream("POST", signed_url,
                                 content=json.dumps(body, ensure_ascii=False),
                                 headers={"content-type": "application/json; encoding=utf-8",
                                          "referer": BASE + "/chat/create-image",
                                          "accept": "text/event-stream"})

    def sse_frames(self, resp: httpx.Response):
        """SSE 响应 → (id, event, data) 逐帧产出。实抓帧形：
        `id: 0` / `event: SSE_HEARTBEAT` / `data: {...}` / 空行分隔。"""
        cur: dict[str, str] = {}
        for line in resp.iter_lines():
            if not line:
                if cur:
                    yield cur.get("event", ""), cur.get("data", ""), cur.get("id", "")
                    cur = {}
                continue
            for prefix, key in (("event:", "event"), ("data:", "data"), ("id:", "id")):
                if line.startswith(prefix):
                    cur[key] = line[len(prefix):].strip()
                    break

    def async_chunk_stream(self, task_id: str, append_scene: int, *,
                           seq_start: int = 0):
        """FETCH_STREAM 切换后的续拉流（POST /chat/async/chunk_stream）。"""
        body = {"task_id": task_id, "seq_start": seq_start, "ext": {},
                "append_scene": append_scene}
        url = self._url(PATH_ASYNC_STREAM)
        return self._http.stream("POST", url,
                                 content=json.dumps(body, ensure_ascii=False),
                                 headers={"content-type": "application/json; encoding=utf-8",
                                          "referer": BASE + "/",
                                          "accept": "text/event-stream"})

    def check_send_rate_limit(self) -> dict:
        """发送频控预检（cmd=2260，免费，浏览器发送前必调）。"""
        db = self._post_bff(PATH_SEND_RATE_LIMIT, envelope(CMD_RATE_LIMIT, {
            "check_message_send_rate_limit_uplink_body": {}}))
        return (db.get("check_message_send_rate_limit_downlink_body") or {})

    def close(self) -> None:
        self._http.close()
