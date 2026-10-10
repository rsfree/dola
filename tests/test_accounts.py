#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""账号池语义：加载、轮询调度、显式点名、失效标记。"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app.accounts import AccountRegistry  # noqa: E402


class _FakeSettings:
    dola_cookie = ""
    upstream_proxy = ""
    device_id = ""
    web_id = ""


def _registry(tmp_path, entries):
    f = tmp_path / "accounts.json"
    f.write_text(json.dumps(entries))
    os_env = _FakeSettings()
    import os
    os.environ["DOLA_ACCOUNTS_FILE"] = str(f)
    os.environ.pop("DOLA_ACCOUNTS", None)
    try:
        return AccountRegistry(os_env)
    finally:
        os.environ.pop("DOLA_ACCOUNTS_FILE", None)


def test_round_robin_across_healthy(tmp_path):
    r = _registry(tmp_path, [{"name": "a", "cookie": "c1"},
                             {"name": "b", "cookie": "c2"}])
    picks = [r.pick().name for _ in range(4)]
    assert picks == ["a", "b", "a", "b"]


def test_dead_account_skipped(tmp_path):
    r = _registry(tmp_path, [{"name": "a", "cookie": "c1"},
                             {"name": "b", "cookie": "c2"}])
    r.mark_dead("a", "cookie 失效")
    picks = {r.pick().name for _ in range(3)}
    assert picks == {"b"}


def test_all_dead_raises(tmp_path):
    r = _registry(tmp_path, [{"name": "a", "cookie": "c1"}])
    r.mark_dead("a", "x")
    with pytest.raises(Exception, match="全部失效"):
        r.pick()


def test_explicit_pick_dead_account_errors_clearly(tmp_path):
    """点名已死账号必须明确报错——静默换号会破坏任务亲和性。"""
    r = _registry(tmp_path, [{"name": "a", "cookie": "c1"},
                             {"name": "b", "cookie": "c2"}])
    r.mark_dead("a", "cookie 失效")
    with pytest.raises(Exception, match="a 已失效"):
        r.pick(prefer="a")


def test_duplicate_name_rejected(tmp_path):
    with pytest.raises(Exception, match="重复"):
        _registry(tmp_path, [{"name": "a", "cookie": "c1"},
                             {"name": "a", "cookie": "c2"}])


def test_client_per_account_is_cached_and_isolated(tmp_path):
    r = _registry(tmp_path, [{"name": "a", "cookie": "c1", "proxy": "http://1.2.3.4:8080"},
                             {"name": "b", "cookie": "c2"}])
    ca1 = r.get("a").client()
    ca2 = r.get("a").client()
    cb = r.get("b").client()
    assert ca1 is ca2, "同账号复用常驻客户端"
    assert ca1 is not cb
    # 出口隔离体现在客户端 proxy 配置
    from app.upstream.dola.client import DolaClient
    assert isinstance(ca1, DolaClient)


def test_node_binding_resolves_per_account_proxy(tmp_path):
    """节点模板含 {account} ⇒ 每账号解析出不同用户名（网关侧粘性 IP 的根基）。"""
    nodes_f = tmp_path / "nodes.json"
    nodes_f.write_text(json.dumps([
        {"id": 2, "name": "livetest-per-account-2090",
         "proxy": "http://{account}:pw@gw.1task.cn:2090"}]))
    from app.nodes import NodeRegistry
    nodes = NodeRegistry(str(nodes_f))
    # 直接造两个绑节点的账号
    from app.accounts import Account
    ra = Account(name="u1", cookie="c1", node_id=2)
    rb = Account(name="u2", cookie="c2", node_id=2)
    # 测我们自己的解析逻辑（httpx 内部结构不进断言）
    pa = nodes.resolve_proxy(2, "u1")
    pb = nodes.resolve_proxy(2, "u2")
    assert "u1:pw@" in pa and "u2:pw@" in pb, "每账号用户名应注入代理模板"
    assert pa != pb
    # 静态节点：两账号同出口
    nodes_f.write_text(json.dumps([
        {"id": 3, "name": "static", "proxy": "http://u:p@5.6.7.8:3128"}]))
    nodes3 = NodeRegistry(str(nodes_f))
    assert nodes3.resolve_proxy(3, "u3") == "http://u:p@5.6.7.8:3128"
    # Account.client 实际采用解析结果（非直配、非直连）
    ca = ra.client(nodes=nodes)
    ca2 = ra.client(nodes=nodes)
    cb = rb.client(nodes=nodes)
    assert ca is ca2, "同账号复用常驻客户端"
    assert ca._http is not cb._http, "不同账号客户端隔离"
