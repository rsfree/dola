#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""账号池 —— 按账号绑定 cookie+出口IP，实现账号隔离（参照 grok.1task.cn 形态）。

来源三选一（优先级高→低）：
  1. DOLA_ACCOUNTS_FILE 指向 JSON：[{"name":"a","cookie":"...","proxy":"http://ip:port"}, ...]
  2. DOLA_ACCOUNTS      环境变量 JSON（同上结构）
  3. DOLA_COOKIE(+DOLA_PROXY) 单账号兜底，name="default"

隔离语义：
  - 同一账号的所有请求（发送+轮询）恒走同一出口 IP/代理；
  - 视频任务的 conv 归创建账号可见 ⇒ 任务必须记录 account 并用同一账号轮询；
  - 上游 712012001（登录失效）⇒ 标记账号 dead，调度器跳过。
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import InvalidParameterError
from .upstream.dola import DolaClient


@dataclass
class Account:
    name: str
    cookie: str
    proxy: str = ""              # 直配代理（优先级高于 node 绑定）
    node_id: int | None = None   # 绑定出口节点（节点 proxy 模板按账号解析）
    #: 运行态
    dead: bool = False
    dead_reason: str = ""
    dead_at: float = 0.0
    inflight: int = 0
    total_ok: int = 0
    total_fail: int = 0
    _client: DolaClient | None = field(default=None, repr=False)

    def client(self, device_id: str = "", web_id: str = "",
               nodes=None) -> DolaClient:
        """每账号一个常驻客户端。出口解析优先级：直配 proxy > 绑定节点 > 直连。"""
        if self._client is None:
            proxy = self.proxy or (nodes.resolve_proxy(self.node_id, self.name)
                                   if nodes is not None else "")
            self._client = DolaClient(self.cookie, device_id=device_id,
                                      web_id=web_id, proxy=proxy or None)
        return self._client

    def snapshot(self, node_name: str = "") -> dict[str, Any]:
        # 🔴 代理脱敏：透传模式下任何调用方都能看 /v1/accounts，凭据不能外露
        proxy_disp = self.proxy or "direct"
        if "@" in proxy_disp:
            scheme, rest = proxy_disp.split("://", 1)
            host = rest.split("@", 1)[1]
            proxy_disp = f"{scheme}://{host}"
        return {"name": self.name, "dead": self.dead,
                "dead_reason": self.dead_reason,
                "proxy": proxy_disp,
                "node": node_name or self.node_id,
                "inflight": self.inflight, "ok": self.total_ok,
                "fail": self.total_fail}


class AccountRegistry:
    def __init__(self, settings, nodes=None) -> None:
        self._lock = threading.Lock()
        self._accounts: dict[str, Account] = {}
        self._rr = 0
        self.nodes = nodes
        self.device_id = settings.device_id
        self.web_id = settings.web_id
        self._load(settings)

    def _load(self, settings) -> None:
        entries: list[dict[str, Any]] = []
        path = os.environ.get("DOLA_ACCOUNTS_FILE", "").strip()
        raw_env = os.environ.get("DOLA_ACCOUNTS", "").strip()
        if path:
            entries = json.loads(Path(path).read_text())
        elif raw_env:
            entries = json.loads(raw_env)
        elif settings.dola_cookie:
            entries = [{"name": "default", "cookie": settings.dola_cookie,
                        "proxy": settings.upstream_proxy}]
        if not entries:
            raise InvalidParameterError(
                "无账号可加载：配 DOLA_ACCOUNTS_FILE / DOLA_ACCOUNTS / DOLA_COOKIE 三者之一")
        seen: set[str] = set()
        for i, e in enumerate(entries):
            name = str(e.get("name") or f"acct{i}").strip()
            if name in seen:
                raise InvalidParameterError(f"账号名重复：{name}")
            seen.add(name)
            cookie = str(e.get("cookie", "")).strip()
            if not cookie:
                raise InvalidParameterError(f"账号 {name} 缺 cookie")
            self._accounts[name] = Account(
                name=name, cookie=cookie,
                proxy=str(e.get("proxy", "")).strip(),
                node_id=e.get("node"))

    # ---- 调度 ----
    def pick(self, prefer: str = "") -> Account:
        """选账号：显式点名 > 健康者轮询。点名账号已死 ⇒ 明确报错（不静默换号，
        任务亲和性优先——换号会看不到原会话）。"""
        with self._lock:
            if prefer:
                a = self._accounts.get(prefer)
                if a is None:
                    raise InvalidParameterError(f"账号不存在：{prefer}")
                if a.dead:
                    raise InvalidParameterError(
                        f"账号 {prefer} 已失效（{a.dead_reason or 'auth'}），请更换 cookie")
                return a
            names = [n for n, a in self._accounts.items() if not a.dead]
            if not names:
                raise InvalidParameterError("账号池全部失效，请补充 cookie")
            names.sort()
            a = self._accounts[names[self._rr % len(names)]]
            self._rr += 1
            return a

    def get(self, name: str) -> Account | None:
        return self._accounts.get(name)

    def mark_ok(self, name: str) -> None:
        with self._lock:
            a = self._accounts.get(name)
            if a:
                a.total_ok += 1

    def mark_dead(self, name: str, reason: str) -> None:
        with self._lock:
            a = self._accounts.get(name)
            if a:
                a.dead = True
                a.dead_reason = reason[:200]
                a.dead_at = time.time()
                a.total_fail += 1

    def mark_fail(self, name: str) -> None:
        with self._lock:
            a = self._accounts.get(name)
            if a:
                a.total_fail += 1

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            out = []
            for a in sorted(self._accounts.values(), key=lambda x: x.name):
                n = self.nodes.get(a.node_id) if (self.nodes and a.node_id is not None) else None
                out.append(a.snapshot(node_name=n.name if n else ""))
            return out
