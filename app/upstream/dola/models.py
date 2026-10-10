#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dola (dola.com) 消息块模型 —— 链上 block → 产物（图像/视频）。

上游契约见 `docs/upstream/dola-api.md` §5。本模块只做**解析**，不发请求。

## 三个硬事实（全部实抓，2026-10-10）

1. 消息 `content` 是 **block 数组的 JSON 字符串**（双重编码）——
   `json.loads(message["content"])` 才是块列表。写坏当场 KeyError，不会静默。

2. 产物在 **`block_type=2074` creation_block**：
   - `type=1` 图像：4 张/组（Seedream 4.5 实测），共享一个 `request_id`；
     `placeholder.description` 是**服务端自报模型名**（"Seedream 4.5"）。
   - `type=2` 视频：`vid` + VOD 系统；`video_model` 又是一层 JSON 字符串，
     里面的 `video_list.video_1.main_url` 是 **base64 编码的播放直链**。

3. **"成功码"不可信**：image.status=2 / video.status=3 才是成品
   （对照 jimeng 的教训：ret=0 ≠ 出片）。本模块的
   `Creation.is_finished` 只认这两个值；非终态一律 `False`。
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any

#: block_type 常量（实抓 + 前端枚举）
BLOCK_TEXT = 10000        # text_block.text
BLOCK_LOADING = 10101     # loading_block：{"text":"正在创作","scene":1}
BLOCK_CREATION = 2074     # creation_block：图像/视频产物

#: creation.type
TYPE_IMAGE = 1
TYPE_VIDEO = 2

#: 产物终态（图像实抓=2；视频实抓=3 —— 两族码不同，别混用）
IMAGE_STATUS_DONE = 2
VIDEO_STATUS_DONE = 3


@dataclass
class ImageArtifact:
    key: str                      # tos-mya-i-<space>/rc_gen_image/<hash>.jpeg
    urls: dict[str, str]          # thumb/ori/ori_raw/preview → 签名 URL
    width: int
    height: int
    status: int
    request_id: str = ""          # 一组 N 张共享
    model: str = ""               # placeholder.description，服务端自报
    prompt: str = ""              # gen_params.prompt（服务端回显）
    ratio: str = ""               # gen_params.ratio
    creation_id: str = ""

    @property
    def is_finished(self) -> bool:
        return self.status == IMAGE_STATUS_DONE

    @property
    def raw_url(self) -> str:
        """优先无水印原图（❓ image_ori_raw 未逐字节比对过水印）。"""
        return self.urls.get("ori_raw") or self.urls.get("ori") or ""


@dataclass
class VideoArtifact:
    vid: str
    status: int
    duration_s: float
    width: int
    height: int
    download_url: str = ""
    cover_url: str = ""
    play_url_1080p: str = ""      # video_model.video_list 里 base64 解出的直链
    definition: str = ""
    creation_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_finished(self) -> bool:
        return self.status == VIDEO_STATUS_DONE

    @property
    def best_url(self) -> str:
        """优先 1080p 播放链，退 download_url。"""
        return self.play_url_1080p or self.download_url


@dataclass
class Creation:
    """creation_block.creations[] 的一个元素。"""
    type: int                     # 1=图 2=视频
    creation_id: str
    task_type: int                # 图像实抓=1，视频实抓=6
    image: ImageArtifact | None = None
    video: VideoArtifact | None = None

    @property
    def is_finished(self) -> bool:
        if self.type == TYPE_IMAGE:
            return bool(self.image and self.image.is_finished)
        if self.type == TYPE_VIDEO:
            return bool(self.video and self.video.is_finished)
        return False


@dataclass
class MessageBlocks:
    """一条消息解析后的视图。"""
    message_id: str
    user_type: int                # 1=用户 2=bot
    texts: list[str] = field(default_factory=list)
    loading: list[str] = field(default_factory=list)
    creations: list[Creation] = field(default_factory=list)

    @property
    def is_generating(self) -> bool:
        """有 loading 块且尚无成品 ⇒ 生成中（保守判据，见模块 docstring 事实 3）。"""
        return bool(self.loading) and not any(c.is_finished for c in self.creations)


def parse_blocks(content: str | list) -> list[dict]:
    """message.content（JSON 字符串或已反序列化的列表）→ 块列表。

    🔴 content 是双重编码；传错类型直接 TypeError，不吞。
    """
    if isinstance(content, list):
        return content
    if not isinstance(content, str):
        raise TypeError(f"content must be str|list, got {type(content)!r}")
    return json.loads(content)


def _decode_b64(u: str) -> str:
    """VOD main_url/backup_url 是标准 base64 的播放直链。"""
    try:
        return base64.b64decode(u).decode("utf-8", "replace")
    except Exception:
        return ""


def parse_creation(entry: dict) -> Creation:
    """creation_block.creations[] 一项 → Creation。字段缺失容忍（上游常加新字段）。"""
    ctype = entry.get("type")
    c = Creation(type=ctype, creation_id=str(entry.get("id", "")),
                 task_type=(entry.get("gen_detail") or {}).get("task_type", -1))
    if ctype == TYPE_IMAGE and isinstance(entry.get("image"), dict):
        im = entry["image"]
        urls: dict[str, str] = {}
        for slot in ("image_thumb", "image_ori", "image_ori_raw", "image_preview"):
            v = im.get(slot)
            if isinstance(v, dict) and v.get("url"):
                urls[slot.replace("image_", "")] = v["url"]
        gp = im.get("gen_params") or {}
        ph = im.get("placeholder") or {}
        c.image = ImageArtifact(
            key=im.get("key", ""),
            urls=urls,
            width=(im.get("image_ori") or {}).get("width", 0) or (ph.get("width") or 0),
            height=(im.get("image_ori") or {}).get("height", 0) or (ph.get("height") or 0),
            status=int(im.get("status", -1)),
            request_id=im.get("request_id", ""),
            model=ph.get("description", ""),
            prompt=gp.get("prompt", ""),
            ratio=str(gp.get("ratio", "")),
            creation_id=c.creation_id,
        )
    elif ctype == TYPE_VIDEO and isinstance(entry.get("video"), dict):
        vd = entry["video"]
        cover = ""
        cv = vd.get("cover") or {}
        it = cv.get("image_preview") or cv.get("image_thumb") or {}
        cover = it.get("url", "")
        play1080, definition = "", ""
        vm = vd.get("video_model")
        if isinstance(vm, str) and vm:
            try:
                vmj = json.loads(vm)
            except json.JSONDecodeError:
                vmj = {}
            vlist = (vmj.get("video_list") or {})
            v1 = vlist.get("video_1") or (next(iter(vlist.values()), {}) if vlist else {})
            play1080 = _decode_b64(v1.get("main_url", ""))
            definition = v1.get("definition", "")
        c.video = VideoArtifact(
            vid=vd.get("vid", ""),
            status=int(vd.get("status", -1)),
            duration_s=float(vd.get("duration") or 0.0),
            width=int(vd.get("width") or 0),
            height=int(vd.get("height") or 0),
            download_url=vd.get("download_url", ""),
            cover_url=cover,
            play_url_1080p=play1080,
            definition=definition,
            creation_id=c.creation_id,
            raw=vd,
        )
    return c


def parse_message(msg: dict) -> MessageBlocks:
    """/im/chain/single 的一条 message → MessageBlocks。"""
    out = MessageBlocks(message_id=str(msg.get("message_id", "")),
                        user_type=int(msg.get("user_type", 0)))
    for b in parse_blocks(msg.get("content", "[]")):
        if not isinstance(b, dict):
            continue
        bt = b.get("block_type")
        content = b.get("content") or {}
        if bt == BLOCK_TEXT and isinstance(content.get("text_block"), dict):
            t = (content["text_block"] or {}).get("text", "")
            if t:
                out.texts.append(t)
        elif bt == BLOCK_LOADING and isinstance(content.get("loading_block"), dict):
            t = (content["loading_block"] or {}).get("text", "")
            if t:
                out.loading.append(t)
        elif bt == BLOCK_CREATION and isinstance(content.get("creation_block"), dict):
            for entry in (content["creation_block"].get("creations") or []):
                out.creations.append(parse_creation(entry))
    return out


def parse_chain_response(downlink_body: dict) -> list[MessageBlocks]:
    """chain/single 的 downlink_body → 消息列表（含 resume 请求同步使用）。"""
    body = downlink_body.get("pull_singe_chain_downlink_body") or {}
    return [parse_message(m) for m in (body.get("messages") or [])]
