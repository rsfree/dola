#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""出口节点（egress nodes）—— 账号隔离的 IP 载体（参照 grok2api egress-nodes）。

来源：DOLA_NODES_FILE JSON：[{"id":2,"name":"livetest-per-account-2090",
       "proxy":"http://{account}:<pass>@gw.host:2090"}, ...]

proxy 模板语义：
  - 含 **{account}** 占位 ⇒ 按账号粘性：网关侧按用户名给每个账号固定 IP
    （102 账号共用一个"节点"、各得一个 IP 的规模化姿势）；
  - 不含占位 ⇒ 该节点所有账号共享同一出口（静态 IP 节点）。

grok2api 对应面（2026-10-10 从 grok.1task.cn 前端取证）：
  /api/admin/v1/egress-nodes{,/{id},/{id}/accounts,/{id}/test,
  /{id}/proxy-url/reveal,/{id}/refresh-clearance}
⇒ 我们取其核心三件：列表（脱敏）、按账号解析、出口实测（test）。
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx


class NodeError(RuntimeError):
    pass


@dataclass
class EgressNode:
    id: int
    name: str
    proxy_template: str = ""
    #: 最近一次实测出口 IP（运行态，不入库）
    last_exit_ip: str = ""
    last_test_at: float = 0.0

    #: 占位符兼容：{account}（英文）与 {账号}（中文，livetest 实际用法）
    _PLACEHOLDERS = ("{account}", "{账号}")

    def resolves_per_account(self) -> bool:
        return any(ph in self.proxy_template for ph in self._PLACEHOLDERS)

    def proxy_for(self, account_name: str) -> str:
        """解析代理串。规范化的两条硬规则：
        1. {account}/{账号} 占位都替换（livetest 网关用中文占位）；
        2. socks5h:// → socks5://（httpx 不认 socks5h scheme；httpcore 按域名
           转发代理解析，语义等效 socks5h）。"""
        if not self.proxy_template:
            return ""
        t = self.proxy_template
        if self.resolves_per_account():
            for ph in self._PLACEHOLDERS:
                t = t.replace(ph, account_name)
        if t.lower().startswith("socks5h://"):
            t = "socks5://" + t[len("socks5h://"):]
        return t

    def snapshot(self) -> dict[str, Any]:
        # 🔴 脱敏：模板里的凭据（user:pass@）不外露，只给 host:port + 占位符提示
        t = self.proxy_template
        masked = "direct"
        if t:
            scheme, _, rest = t.partition("://")
            host = rest.rsplit("@", 1)[-1]
            masked = f"{scheme}://{host}" + ("  (per-account)" if "{account}" in t else "")
        return {"id": self.id, "name": self.name, "proxy": masked,
                "per_account": self.resolves_per_account(),
                "last_exit_ip": self.last_exit_ip,
                "last_test_at": self.last_test_at}


class NodeRegistry:
    def __init__(self, path: str | None = None) -> None:
        self._lock = threading.Lock()
        self._nodes: dict[int, EgressNode] = {}
        if path and Path(path).exists():
            self._load(path)

    def _load(self, path: str) -> None:
        for e in json.loads(Path(path).read_text()):
            node = EgressNode(id=int(e["id"]), name=str(e.get("name") or f"node{e['id']}"),
                              proxy_template=str(e.get("proxy", "")))
            self._nodes[node.id] = node

    def get(self, node_id: int | None) -> EgressNode | None:
        if node_id is None:
            return None
        return self._nodes.get(int(node_id))

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [n.snapshot() for n in sorted(self._nodes.values(), key=lambda x: x.id)]

    def resolve_proxy(self, node_id: int | None, account_name: str) -> str:
        """账号 → 出口代理串。节点不存在/无模板 ⇒ 空串（直连）。"""
        n = self.get(node_id)
        return n.proxy_for(account_name) if n else ""

    def test_exit(self, node_id: int, account_name: str = "probe",
                  timeout: float = 12.0) -> dict[str, Any]:
        """实测出口 IP：经该节点（按账号解析代理）请求 ipify。

        同节点两个账号测试得到不同 IP ⇒ per-account 粘性生效（隔离自证）。
        """
        n = self.get(node_id)
        if n is None:
            raise NodeError(f"节点不存在：{node_id}")
        proxy = n.proxy_for(account_name)
        with httpx.Client(timeout=timeout, trust_env=False,
                          proxy=proxy or None) as h:
            r = h.get("https://api.ipify.org?format=json")
            r.raise_for_status()
            ip = str(r.json().get("ip", ""))
        with self._lock:
            n.last_exit_ip = ip
            n.last_test_at = time.time()
        return {"node_id": node_id, "account": account_name, "exit_ip": ip,
                "per_account": n.resolves_per_account()}
