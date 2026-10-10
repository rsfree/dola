#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dola-service 错误体系 —— 对外信封 + 上游码映射。

上游错误码语义见 `docs/upstream/dola-api.md`；分类决定重试语义（ jimeng 纪律：
额度类重试无效、风控类重试加剧、限流类可退避）。
"""
from __future__ import annotations

from typing import Any


class AdapterError(RuntimeError):
    status_code = 500
    err_type = "adapter_error"

    def __init__(self, message: str, *, code: str | None = None,
                 upstream: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code or self.err_type
        self.upstream = upstream or {}


class InvalidParameterError(AdapterError):
    status_code = 400
    err_type = "invalid_parameter"


class AuthError(AdapterError):
    status_code = 401
    err_type = "auth_error"


class UpstreamUnavailable(AdapterError):
    """上游可达性问题（网络/地理/网关）—— 可退避重试。"""
    status_code = 502
    err_type = "upstream_unavailable"


class UpstreamAuthError(AdapterError):
    """上游凭据失效（712012001/710012001）—— 重试无效，必须换 cookie。"""
    status_code = 502
    err_type = "upstream_auth"
    status_code_override = 502


class UpstreamRiskError(AdapterError):
    """shark 风控拦截（710022004）—— 签名缺失/失效，重铸再试一次。"""
    status_code = 502
    err_type = "upstream_risk"


class QuotaExceeded(AdapterError):
    """上游额度耗尽（视频 2 条/日档位、图像日额度）—— 重试无效。"""
    status_code = 429
    err_type = "quota_exceeded"


def classify_upstream(code: int | str | None, msg: str = "") -> AdapterError:
    """上游错误码 → 本服务错误。新码见到再补表（出处记 docstring）。"""
    c = str(code) if code is not None else ""
    if c in ("712012001", "710012001"):
        return UpstreamAuthError(f"上游登录校验失败（{c}）：cookie 过期，换 DOLA_COOKIE")
    if c == "712012002":
        return UpstreamUnavailable(f"上游信封被拒（712012002）：content-type/编码层错误")
    if c == "710022003":
        return UpstreamUnavailable("上游地理围栏（710022003）：写路径需配置 DOLA_PROXY")
    if c == "710022004":
        return UpstreamRiskError("上游风控拦截（710022004）：a_bogus 缺失/失效，需重铸签名")
    if c == "710020202":
        return AdapterError(f"上游参数被拒（710020202）：{msg or '发送体形态错误'}",
                            code="upstream_param")
    if "rate limited" in msg.lower() or c == "710022004":
        return UpstreamRiskError("上游风控拦截")
    return AdapterError(f"上游错误（code={c or 'unknown'}）：{msg}", code="upstream_error")
