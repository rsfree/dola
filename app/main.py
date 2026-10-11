#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dola-service —— 对外门面（生产标准）。

契约（docs/INTERFACE.md，冻结）：
  POST /v1/images/generations              同步出图（创建+轮询合并）
  POST /async/v1/images/generations        受理（202，只回 task_id）
  GET  /async/v1/images/generations/{id}   查询（不存在/非属主一律 404）
  POST /api/v3/contents/generations/tasks  视频唯一入口（火山方舟契约）
  GET  /api/v3/contents/generations/tasks/{id}
  GET  /v1/models                          公开能力清单
  GET  /healthz /readyz                    探活（免鉴权）

写路径三级门（docs §4）：地理（代理）→ 鉴权（sessionid）→ shark（a_bogus 铸签）。
"""
from __future__ import annotations

import json
import os
import threading
import time
from contextlib import asynccontextmanager
from typing import Any, Iterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .accounts import AccountRegistry
from .nodes import NodeError, NodeRegistry
from .config import ConfigError, load_settings, Settings
from .errors import (AdapterError, AuthError, InvalidParameterError,
                     UpstreamUnavailable,
                     QuotaExceeded, UpstreamAuthError, UpstreamRiskError,
                     classify_upstream)
from .store import TaskStore, key_fingerprint
from .upstream.dola import (DolaAuthError, DolaClient, DolaError,
                            build_completion_body, parse_chain_response)
from .upstream.dola.models import TYPE_IMAGE, TYPE_VIDEO
from .upstream.dola.signer import SignerClient, SignerError

# ---------------------------------------------------------------- 模型注册表
# 只登记**验证过**的键；未验证的模型键宁可 400 也不瞎猜（上游 ic_mini 之外的
# 内部键未实抓，猜错 = 710020202）。
# 火山方舟风格别名（同一模型多个入口名；newapi 用 Ark 命名也能路由）
_IMG_CFG = {"skill": 3, "ability_model": None, "verified": True}
_V25_CFG = {"skill": 17, "ability_model": "seedance_v2.5", "duration": 10, "verified": True}
_V10_CFG = {"skill": 17, "ability_model": "ic_mini", "duration": 10, "verified": True}
IMAGE_MODELS = {
    "dola-seedream-4.5": _IMG_CFG,
    # Ark 对齐名
    "doubao-seedream-4.5": _IMG_CFG,
    "doubao-seedream-4-5": _IMG_CFG,
}
VIDEO_MODELS = {
    "dola-seedance-1-0": _V10_CFG,
    "dola-seedance-2-5": _V25_CFG,
    # Ark 对齐名
    "doubao-seedance-1-0": _V10_CFG,
    "doubao-seedance-1-0-lite": _V10_CFG,
    "doubao-seedance-2-5": _V25_CFG,
    "doubao-seedance-2-5-pro": _V25_CFG,
    "doubao-seedance-2-0": _V25_CFG,
}


class Settings_holder:
    pass


# ---------------------------------------------------------------- 请求模型
class ImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)
    model: str = "dola-seedream-4.5"
    ratio: str = "1:1"


class ArkVideoRequest(BaseModel):
    model: str
    content: list[dict[str, Any]] = Field(min_length=1)
    duration: int = 10

    @property
    def prompt(self) -> str:
        for c in self.content:
            if c.get("type") == "text":
                return str(c.get("text", ""))
        raise InvalidParameterError("content 缺少 text 项")


# ---------------------------------------------------------------- 发送内核
def _submit(ac_client: DolaClient, signer: SignerClient, *, prompt: str,
            skill: int, ability_param: dict,
            ref_attachment_uri: str | None = None) -> tuple[str, str]:
    """铸签 → 发送 → 返回 (conversation_id, 首帧信号)。

    风控 710022004 ⇒ 作废缓存重铸一次（重试语义：只重试一次，风控重试加剧）。
    """
    body = build_completion_body(prompt=prompt, skill_type=skill,
                                 ability_param=ability_param)
    if ref_attachment_uri:
        # 🔴 图生图契约（用户浏览器实抓 2026-10-10）：附件消息(block_type 10052)
        #    与文本消息并列两条；文本自带技能前缀
        prefix = "生成图片：" if skill == 3 else "生成视频："
        att = {"local_message_id": str(uuid.uuid1()),
               "content_block": [{"block_type": 10052,
               "content": {"attachment_block": {"attachments": [{"type": 1,
                   "identifier": str(uuid.uuid1()),
                   "image": {"name": "reference.jpg", "uri": ref_attachment_uri,
                             "image_ori": {"url": "", "width": 0, "height": 0,
                                           "format": "", "url_formats": {}},
                             "parse_state": 0, "review_state": 1,
                             "upload_status": 1, "progress": 100, "src": ""}}]},
                           "pc_event_block": ""},
               "block_id": str(uuid.uuid4()), "parent_id": "",
               "meta_info": [], "append_fields": []}],
               "message_status": 0}
        base_msgs = body["messages"] or [{"local_message_id": str(uuid.uuid1()),
                                          "content_block": [], "message_status": 0}]
        txt = dict(base_msgs[0])
        tb = txt.get("content_block") or []
        if tb and (tb[0].get("content", {}).get("text_block")):
            tb[0]["content"]["text_block"]["text"] = f"{prefix}{prompt}"
        body["messages"] = [att, txt]
    body_str = json.dumps(body, ensure_ascii=False)
    base_url = f"{ac_client._url('/chat/completion')}"
    try:
        signed = signer.sign(base_url, body_str)
    except SignerError as e:
        # 铸签 sidecar 挂了/超时：502 可退避（sidecar 自带页面自愈）
        raise UpstreamUnavailable(f"铸签失败：{e}")
    last_err: AdapterError | None = None
    for attempt in (1, 2):
        try:
            with ac_client.send_completion_signed(signed, body) as resp:
                ct = resp.headers.get("content-type", "")
                if "event-stream" not in ct:
                    # 地理围栏等：HTTP 200 + JSON（docs §4），非 SSE
                    payload = json.loads(b"".join(resp.iter_bytes()).decode())
                    raise classify_upstream(payload.get("code"),
                                            payload.get("msg", ""))
                conv_id = ""
                for event, data, _fid in ac_client.sse_frames(resp):
                    if not data:
                        continue
                    if event == "STREAM_ERROR":
                        d = json.loads(data)
                        raise classify_upstream(d.get("error_code"),
                                                d.get("error_msg", ""))
                    if event == "SSE_ACK":
                        ack = json.loads(data)
                        conv_id = str((ack.get("ack_client_meta") or {})
                                      .get("conversation_id") or "")
                        if conv_id:
                            return conv_id, "ack"
                if conv_id:
                    return conv_id, "ack"
                raise UpstreamRiskError("SSE 无 ACK 结束（疑似风控静默）")
        except UpstreamRiskError as e:
            last_err = e
            signer.invalidate(base_url, body_str)
            if attempt == 1:
                signed = signer.sign(base_url, body_str, force=True)
                continue
            raise
    raise last_err or AdapterError("submit failed")


def _poll(client: DolaClient, conv_id: str, kind: str, *,
          timeout: float, interval: float) -> dict:
    """轮询消息链到终态。返回 {'status':..., 'arts': [creation...], 'texts': [...]}"""
    want = TYPE_IMAGE if kind == "image" else TYPE_VIDEO
    deadline = time.time() + timeout
    last_texts: list[str] = []
    while time.time() < deadline:
        msgs = parse_chain_response(client.chain_single_raw(conv_id))
        arts = [c for m in msgs for c in m.creations if c.type == want]
        other = [c for m in msgs for c in m.creations if c.type != want]
        last_texts = [t for m in msgs for t in m.texts]
        # 🔴 错配技能快速失败：视频请求被上游当图像生成（前缀缺失实弹踩过）
        if not arts and other and any(c.is_finished for c in other):
            kinds = {("image" if c.type == TYPE_IMAGE else "video") for c in other}
            raise AdapterError(
                f"上游按错误技能出产物（期望 {kind}，实得 {sorted(kinds)}）——"
                "检查发送文本前缀", code="skill_mismatch")
        if arts:
            done = all(c.is_finished for c in arts)
            if done:
                return {"status": "succeeded", "arts": arts, "texts": last_texts}
        # 🔴 额度拦截判据要窄：bot 信息性 ack（"将消耗 2 个额度"）含"额度"但不是拒绝
        #    （Seedance 2.5 实测踩过）。真拒绝 = "达到上限"/"额度不足"且无产物在途。
        for t in last_texts:
            if ("达到上限" in t or "额度不足" in t or "无法生成" in t) and not arts:
                raise QuotaExceeded(t.strip())
        time.sleep(interval)
    return {"status": "timeout", "arts": [], "texts": last_texts}


def _generation_with_failover(registry: AccountRegistry, store: TaskStore,
                              signer: SignerClient, settings: Settings, lock,
                              *, task_id: str, kind: str, prompt: str,
                              model_key: str, prefer: str = "",
                              ability_extra: dict | None = None,
                              ref_attachment_uri: str | None = None) -> None:
    """生成任务 + 🔴 满额换号：QuotaExceeded ⇒ 标记账号到次日 ⇒ 换下一个健康账号重试。"""
    from .errors import QuotaExceeded as _QE
    from .upstream.dola.send_body import SKILL_IMAGE, SKILL_VIDEO
    skill = 3 if kind == "image" else 17
    tried: set[str] = set()
    quota_err: str | None = None
    attempts = 0
    while attempts < 8:
        acct = registry.pick(prefer=prefer, for_generation=True)
        if acct.name in tried:
            break
        tried.add(acct.name)
        attempts += 1
        ac_client = _client_of_local(registry, acct)
        try:
            ap = dict(ability_extra or {})
            with lock:
                conv_id, _ = _submit(ac_client, signer, prompt=prompt,
                                     skill=skill, ability_param=ap or None,
                                     ref_attachment_uri=ref_attachment_uri)
            store.update(task_id, conv_id=conv_id, status="running",
                         account=acct.name)
            res = _poll(ac_client, conv_id, kind,
                        timeout=(settings.image_poll_timeout if kind == "image"
                                 else settings.video_poll_timeout),
                        interval=settings.poll_interval)
            registry.mark_ok(acct.name)
            if res["status"] == "succeeded":
                if kind == "image":
                    store.update(task_id, status="succeeded",
                                 upstream={"data": _images_payload(res["arts"])})
                else:
                    store.update(task_id, status="succeeded",
                                 upstream=_video_payload(res["arts"][0]))
                return
            store.update(task_id, status="failed", error="timeout")
            return
        except _QE as e:
            # 🔴 满额换号：额度打满 ⇒ 标记到次日 ⇒ 换号重试
            registry.mark_exhausted(acct.name)
            quota_err = str(e)
            continue
        except UpstreamAuthError as e:
            registry.mark_dead(acct.name, "712012001 cookie 失效")
            store.update(task_id, status="failed", error=str(e))
            return
        except AdapterError as e:
            registry.mark_fail(acct.name)
            store.update(task_id, status="failed", error=str(e))
            return
        except Exception as e:
            store.update(task_id, status="failed", error=f"internal: {e}")
            return
    store.update(task_id, status="failed",
                 error=quota_err or "无可用账号（全部额度耗尽/失效）",
                 upstream={"code": "all_accounts_exhausted"})


def _client_of_local(registry: AccountRegistry, acct) -> DolaClient:
    return acct.client(registry.device_id, registry.web_id,
                       nodes=registry.nodes)


def _images_payload(arts) -> list[dict[str, Any]]:
    out = []
    for c in arts:
        if c.image:
            out.append({"url": c.image.raw_url, "size": f"{c.image.width}x{c.image.height}",
                        "model": c.image.model, "watermark": False})
    return out


def _video_payload(a) -> dict[str, Any]:
    v = a.video
    return {"video_url": v.best_url, "vid": v.vid,
            "duration": v.duration_s, "definition": v.definition,
            "resolution": f"{v.width}x{v.height}", "watermark": False}


# ---------------------------------------------------------------- app 工厂
def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    settings.validate()
    # 🔴 鉴权默认 = Bearer 透传（key 即身份）；API_KEYS 非空才切白名单。
    #    透传是默认姿态而非配置失误，但公网裸奔依然是事故，所以保留 WARNING。
    import logging
    _log = logging.getLogger("dola-service")
    if settings.auth_mode == "passthrough":
        _log.warning(
            "鉴权模式 = Bearer 透传（默认）：任意非空 Bearer 即身份，"
            "请确保服务部署在网关/内网之后；要收紧请配置 API_KEYS")
    else:
        _log.info("鉴权模式 = 白名单（API_KEYS 已配置）")

    store = TaskStore(settings.db_path)
    signer = SignerClient(settings.signer_url, timeout=settings.signer_timeout,
                          cache_ttl=settings.sign_cache_ttl)
    nodes = NodeRegistry(os.environ.get("DOLA_NODES_FILE", "").strip() or None)
    registry = AccountRegistry(settings, nodes=nodes)
    lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> Iterator[None]:
        yield
        signer.close()
        store.close()

    app = FastAPI(title="dola-service", version="1.0.0", lifespan=lifespan)

    # ---- 账号选择（grok.1task.cn 式账号-IP 隔离）----
    # ---- 🔴 鉴权 = Bearer sessionid 透传 ----
    # new-api 渠道绑 dola 账号 sessionid 做 API key；
    # Bearer token 即上游凭据，服务拆 Bearer → 建 client → 打上游。
    _bearer_clients: dict[str, DolaClient] = {}
    _bearer_lock = threading.Lock()

    def _bearer(request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or not auth[7:].strip():
            raise AuthError("缺少 Authorization: Bearer <dola_sessionid>")
        return auth[7:].strip()

    def _client_for(request: Request) -> DolaClient:
        token = _bearer(request)
        return _client_for_bearer(token)

    def _client_for_bearer(token: str) -> DolaClient:
        with _bearer_lock:
            cl = _bearer_clients.get(token)
            if cl is None:
                cookie = token  # Bearer 透传
                # 🔴 按 sessionid 匹配账号池 → 用完整 cookie（含 ttwid/csrf 等）
                acct = registry.get_by_sessionid(token)
                if acct:
                    cookie = acct.cookie
                cl = DolaClient(cookie, device_id=settings.device_id,
                                web_id=settings.web_id,
                                proxy=settings.upstream_proxy or None)
                _bearer_clients[token] = cl
            return cl

    def _fp(request: Request) -> str:
        return key_fingerprint(_bearer(request))
        return key_fingerprint(_bearer(request))

    @app.exception_handler(AdapterError)
    async def _adapter_error(_r: Request, exc: AdapterError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code,
                            content={"error": {"type": exc.code,
                                               "message": str(exc),
                                               "upstream": exc.upstream}})

    # ---- 探活 ----
    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    @app.get("/readyz")
    def readyz() -> dict:
        try:
            h = signer.healthz()
            return {"ok": bool(h.get("ok")), "signer": h}
        except Exception as e:
            return JSONResponse(status_code=503,
                                content={"ok": False, "signer_error": str(e)[:200]})

    # ---- 出口节点 ----
    @app.get("/v1/nodes")
    def nodes_list(request: Request = None) -> dict:  # type: ignore[assignment]
        _bearer(request)
        return {"object": "list", "data": nodes.list()}

    @app.get("/v1/nodes/{node_id}/test")
    def nodes_test(node_id: int, request: Request = None,
                   account: str = "probe") -> dict:  # type: ignore[assignment]
        """实测节点出口 IP；同节点换 account 名测得不同 IP ⇒ per-account 粘性生效。"""
        _bearer(request)
        try:
            return nodes.test_exit(node_id, account_name=account)
        except NodeError as e:
            raise InvalidParameterError(str(e))
        except Exception as e:
            raise UpstreamUnavailable(f"节点出口测试失败：{e}")

    # ---- 账号池（隔离状态）----
    @app.get("/v1/accounts")
    def accounts(request: Request = None) -> dict:  # type: ignore[assignment]
        _bearer(request)
        return {"object": "list", "data": registry.snapshot()}

    # ---- 公开能力清单 ----
    @app.get("/v1/models")
    def models() -> dict:
        return {"object": "list", "data":
                [{"id": k, "object": "model", "owned_by": "dola",
                  "kind": "image"} for k in IMAGE_MODELS] +
                [{"id": k, "object": "model", "owned_by": "dola",
                  "kind": "video"} for k in VIDEO_MODELS]}

    # ---- 图像：同步 ----
    @app.post("/v1/images/generations")
    def images_sync(req: ImageRequest, request: Request = None) -> dict:  # type: ignore[assignment]
        _bearer(request)
        reg = IMAGE_MODELS.get(req.model)
        if not reg:
            raise InvalidParameterError(f"未知图像模型 {req.model}；"
                                        f"可用：{sorted(IMAGE_MODELS)}")
        ap: dict[str, Any] = {"input_box_content": {
            "user_input_content": req.prompt,
            "reply_message_format": "生成图片：%s"}}
        if req.ratio:
            ap["ratio"] = req.ratio
        ac_client = _client_for(request)
        try:
            with lock:
                conv_id, _ = _submit(ac_client, signer, prompt=req.prompt,
                                     skill=reg["skill"], ability_param=ap)
            res = _poll(ac_client, conv_id, "image",
                        timeout=settings.image_poll_timeout,
                        interval=settings.poll_interval)
        except UpstreamAuthError:
            raise
        if res["status"] != "succeeded":
            raise AdapterError(f"出图超时（{settings.image_poll_timeout}s）",
                               code="generation_timeout")
        return {"created": int(time.time()), "data": _images_payload(res["arts"]),
                "conversation_id": conv_id}

    # ---- 图像：异步 ----
    @app.post("/async/v1/images/generations", status_code=202)
    def images_async(req: ImageRequest, request: Request = None) -> dict:  # type: ignore[assignment]
        fp = _fp(request)
        reg = IMAGE_MODELS.get(req.model)
        if not reg:
            raise InvalidParameterError(f"未知图像模型 {req.model}")
        task_id = store.create("image", fp, req.prompt, req.model)
        def _run() -> None:
            try:
                ap = {"input_box_content": {
                    "user_input_content": req.prompt,
                    "reply_message_format": "生成图片：%s"}}
                if req.ratio:
                    ap["ratio"] = req.ratio
                ac_client = _client_for_bearer(bearer_token)
                with lock:
                    conv_id, _ = _submit(ac_client, signer, prompt=req.prompt,
                                         skill=reg["skill"], ability_param=ap)
                store.update(task_id, conv_id=conv_id, status="running")
                res = _poll(ac_client, conv_id, "image",
                            timeout=settings.image_poll_timeout,
                            interval=settings.poll_interval)
                if res["status"] == "succeeded":
                    store.update(task_id, status="succeeded",
                                 upstream={"data": _images_payload(res["arts"])})
                else:
                    store.update(task_id, status="failed", error="timeout")
            except UpstreamAuthError:
                store.update(task_id, status="failed", error="account auth failed")
            except AdapterError as e:
                store.update(task_id, status="failed", error=str(e))
            except Exception as e:  # 后台线程兜底，绝不哑死
                store.update(task_id, status="failed", error=f"internal: {e}")
        threading.Thread(target=_run, daemon=True).start()
        return {"task_id": task_id, "status": "queued"}

    @app.get("/async/v1/images/generations/{task_id}")
    def images_status(task_id: str, request: Request = None) -> dict:  # type: ignore[assignment]
        row = store.get(task_id)
        if row is None:
            raise HTTPException(status_code=404, detail="not found")
        out = {"task_id": task_id, "status": row["status"],
               "model": row["model"], "prompt": row["prompt"],
               "account": row.get("account", "default"),
               "created_at": row["created_at"]}

        if row["upstream"]:
            out["data"] = json.loads(row["upstream"]).get("data")
        if row["error"]:
            out["error"] = row["error"]
        return out

    @app.get("/async/v1/images/generations")
    def images_list(request: Request = None) -> dict:  # type: ignore[assignment]
        return {"object": "list",
                "data": store.list_owned(_fp(request))}

    @app.delete("/async/v1/images/generations/{task_id}")
    def images_delete(task_id: str, request: Request = None) -> dict:  # type: ignore[assignment]
        if not store.delete_finished(task_id):
            raise HTTPException(status_code=400,
                                detail="不存在/非属主/非终态")
        return {"deleted": True}

    # ---- 视频：方舟契约 ----
    @app.post("/api/v3/contents/generations/tasks")
    def video_create(req: ArkVideoRequest, request: Request = None) -> dict:  # type: ignore[assignment]
        fp = _fp(request)
        reg = VIDEO_MODELS.get(req.model)
        if not reg:
            raise InvalidParameterError(f"未知视频模型 {req.model}；"
                                        f"可用：{sorted(VIDEO_MODELS)}")
        task_id = store.create("video", fp, req.prompt, req.model)
        ap = {"model": reg["ability_model"], "duration": req.duration,
              "input_box_content": {"user_input_content": req.prompt,
                                    "reply_message_format": "生成视频：%s"}}
        def _run() -> None:
            # 🔴 满额换号：QuotaExceeded ⇒ 标记到次日 ⇒ 自动换下一个账号重试
                _generation_with_failover(registry, store, signer, settings, lock,
                                      task_id=task_id, kind="video",
                                      prompt=req.prompt, model_key=req.model,
                                      ability_extra=ap)
        threading.Thread(target=_run, daemon=True).start()
        return {"id": task_id, "model": req.model, "status": "queued"}

    @app.get("/api/v3/contents/generations/tasks/{task_id}")
    def video_status(task_id: str, request: Request = None) -> dict:  # type: ignore[assignment]
        row = store.get(task_id)
        if row is None:
            raise HTTPException(status_code=404, detail="not found")
        status = {"queued": "queued", "running": "running",
                  "succeeded": "succeeded", "failed": "failed"}[row["status"]]

        out: dict[str, Any] = {"id": task_id, "model": row["model"],
                               "status": status, "account": row.get("account", "default")}
        if row["status"] == "succeeded" and row["upstream"]:
            out["content"] = {"video_url": json.loads(row["upstream"]).get("video_url")}
        if row["error"]:
            out["error"] = row["error"]
        return out

    return app
