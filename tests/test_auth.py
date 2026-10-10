#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""鉴权语义回归：Bearer 透传（jimeng/new-api 形态）。

- key 即身份（HMAC 指纹 → 任务归属），服务不维护账号体系
- API_KEYS 空 = 透传模式（任意非空 Bearer）；非空 = 白名单
- 缺 Bearer 一律 401；/v1/models /healthz 免鉴权
"""
from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402


def _client(tmp: str, api_keys: str | None):
    os.environ["DOLA_COOKIE"] = "sessionid=x"
    os.environ["SIGNER_URL"] = "http://127.0.0.1:8491"
    os.environ["DB_PATH"] = tmp
    if api_keys is None:
        os.environ.pop("API_KEYS", None)
    else:
        os.environ["API_KEYS"] = api_keys
    from app.main import create_app
    return TestClient(create_app())


def test_passthrough_accepts_any_bearer(tmp_path):
    c = _client(str(tmp_path / "a.sqlite3"), None)
    assert c.get("/async/v1/images/generations",
                 headers={"Authorization": "Bearer k1"}).status_code == 200
    assert c.get("/async/v1/images/generations",
                 headers={"Authorization": "Bearer k2"}).status_code == 200


def test_missing_bearer_is_401_even_in_passthrough(tmp_path):
    c = _client(str(tmp_path / "b.sqlite3"), None)
    assert c.get("/async/v1/images/generations").status_code == 401


def test_bearer_passthrough_accepts_any_format(tmp_path):
    """Bearer = cookie 串透传，任意非空值即身份（new-api 渠道绑 sessionid/全量 cookie）。"""
    c = _client(str(tmp_path / "c.sqlite3"), None)
    assert c.get("/async/v1/images/generations",
                 headers={"Authorization": "Bearer anything"}).status_code == 200


def test_models_and_healthz_are_public(tmp_path):
    c = _client(str(tmp_path / "d.sqlite3"), "good-key")
    assert c.get("/v1/models").status_code == 200
    assert c.get("/healthz").status_code == 200
