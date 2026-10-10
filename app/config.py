#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dola-service 配置。

纪律同 jimeng：每个旋钮必须有人读、默认值必须能说出依据；配置错误启动即炸。
"""
from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field

_TRUE = {"1", "true", "yes", "on", "y", "t"}


class ConfigError(RuntimeError):
    pass


def _s(key: str, default: str = "") -> str:
    v = os.environ.get(key)
    return default if v is None else v.strip()


def _i(key: str, default: int) -> int:
    raw = _s(key)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ConfigError(f"{key} 必须是整数，实得 {raw!r}") from e


def _b(key: str, default: bool) -> bool:
    return _s(key, "1" if default else "0").lower() in _TRUE


@dataclass(frozen=True)
class Settings:
    # -- 上游凭据 --
    #: 🔴 最小凭据 = cookie 单键 sessionid（docs/upstream/dola-api.md §1 负对照实锤）。
    #: 传整串 cookie 也兼容（客户端会带全量）。
    dola_cookie: str = field(default_factory=lambda: _s("DOLA_COOKIE"))
    #: 🔴 写路径地理围栏（§4）：国内出口直连被拒（710022003），必须走代理；
    #:    读侧不需要。空 = 直连（海外部署）。
    upstream_proxy: str = field(default_factory=lambda: _s("DOLA_PROXY"))
    device_id: str = field(default_factory=lambda: _s("DOLA_DEVICE_ID"))
    web_id: str = field(default_factory=lambda: _s("DOLA_WEB_ID"))

    # -- 铸签 sidecar --
    #: 铸签服务地址（shark 风控要求 a_bogus，§4.0.1）。空 = 拒绝一切写请求。
    signer_url: str = field(default_factory=lambda: _s("SIGNER_URL", ""))
    signer_timeout: float = field(default_factory=lambda: _f_env("SIGNER_TIMEOUT", 30.0))
    #: a_bogus 实测 TTL ≥ 5min（§4.0.1），留余量按 4min 轮换。
    sign_cache_ttl: float = field(default_factory=lambda: _f_env("SIGN_CACHE_TTL", 240.0))

    # -- 服务面 --
    #: 🔴 Bearer 透传语义（对齐 jimeng / new-api 网关形态）：
    #:    Bearer key 即调用方身份（HMAC 指纹做任务归属），服务不维护账号体系。
    #:    - API_KEYS **为空** = 透传模式：接受任意非空 Bearer（网关已鉴权的前置假设），
    #:      启动打 WARNING（仅限内网/网关后部署）。
    #:    - API_KEYS 非空 = 白名单模式：key 必须在名单内。
    api_keys: str = field(default_factory=lambda: _s("API_KEYS"))
    host: str = field(default_factory=lambda: _s("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: _i("PORT", 8490))
    db_path: str = field(default_factory=lambda: _s("DB_PATH", "data/dola.sqlite3"))

    # -- 轮询 --
    poll_interval: float = field(default_factory=lambda: _f_env("POLL_INTERVAL", 5.0))
    image_poll_timeout: float = field(default_factory=lambda: _f_env("IMAGE_POLL_TIMEOUT", 120.0))
    video_poll_timeout: float = field(default_factory=lambda: _f_env("VIDEO_POLL_TIMEOUT", 600.0))

    def validate(self) -> None:
        problems = []
        # DOLA_COOKIE 由 AccountRegistry 兜底检查（账号池三来源任一即可）
        if not self.signer_url:
            problems.append("SIGNER_URL 未配置（写路径必须有铸签 sidecar）")
        if problems:
            raise ConfigError("；".join(problems))

    @property
    def auth_mode(self) -> str:
        """whitelist（API_KEYS 非空）| passthrough（空，Bearer 即身份）。"""
        return "whitelist" if self.api_keys else "passthrough"


def _f_env(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as e:
        raise ConfigError(f"{key} 必须是数字，实得 {raw!r}") from e


def load_settings() -> Settings:
    return Settings()
