#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""铸签 sidecar 客户端 —— a_bogus 的获取与缓存。

sidecar 契约（signer/server.js）：
  GET  /healthz            -> {"ok": true, "page_ready": bool}
  POST /sign               -> {"url": "<含 msToken+a_bogus 的最终签名URL>"}
      body: {"url": "<目标完整URL(未签名)>", "method": "POST", "body": "<字符串>"}
  零副作用：sidecar 内用 CDP Fetch 域拦截签名后的请求，网络层不真发。

a_bogus 语义（docs §4.0.1）：签名 = f(path+query, body, UA, 时间)；
TTL ≥ 5min；重放幂等（local_message_id 去重）。缓存按 (url_without_ts, body_hash)。
"""
from __future__ import annotations

import hashlib
import threading
import time
from typing import Any

import httpx


class SignerError(RuntimeError):
    pass


class SignerClient:
    def __init__(self, base_url: str, timeout: float = 30.0,
                 cache_ttl: float = 240.0) -> None:
        self.base = base_url.rstrip("/")
        self._http = httpx.Client(timeout=timeout, trust_env=False)
        self._ttl = cache_ttl
        self._cache: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def healthz(self) -> dict[str, Any]:
        r = self._http.get(f"{self.base}/healthz")
        r.raise_for_status()
        return r.json()

    def sign(self, url: str, body: str, *, method: str = "POST",
             force: bool = False) -> str:
        """返回带 a_bogus 的最终签名 URL。

        缓存键 = 完整 URL + body 摘要（a_bogus 覆盖两者；TTL 内复用）。
        force=True 跳过缓存（重试时上一次签名可能已被标记失效）。
        """
        key = url + "|" + hashlib.sha1(body.encode()).hexdigest()
        if not force:
            with self._lock:
                hit = self._cache.get(key)
                if hit and time.time() - hit[0] < self._ttl:
                    return hit[1]
        r = self._http.post(f"{self.base}/sign",
                            json={"url": url, "method": method, "body": body})
        if r.status_code != 200:
            raise SignerError(f"signer {r.status_code}: {r.text[:200]}")
        signed = r.json().get("url")
        if not signed or "a_bogus=" not in signed:
            raise SignerError(f"signer 返回缺 a_bogus: {str(signed)[:120]}")
        with self._lock:
            self._cache[key] = (time.time(), signed)
        return signed

    def invalidate(self, url: str, body: str) -> None:
        """上游报 710022004（风控）时调：这份签名已失效。"""
        key = url + "|" + hashlib.sha1(body.encode()).hexdigest()
        with self._lock:
            self._cache.pop(key, None)

    def close(self) -> None:
        self._http.close()
