#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 2026-10-10 实抓的两条消息链做回归向量。

- probe/chain_image_full.json  —— 图像生成会话（4 张 2048²，Seedream 4.5）
- probe/chain_single_body.json —— 视频历史会话（生成猫视频，VOD 1080p）
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.upstream.dola.models import (TYPE_IMAGE, TYPE_VIDEO,
                                      parse_chain_response, parse_message)

PROBE = pathlib.Path(__file__).resolve().parents[1] / "probe"


def _load(name: str) -> dict:
    return json.loads((PROBE / name).read_text())


def _image_messages() -> list:
    j = _load("chain_image_full.json")
    return j["downlink_body"]["pull_singe_chain_downlink_body"]["messages"]


def _video_messages() -> list:
    j = _load("chain_single_body.json")
    return j["downlink_body"]["pull_singe_chain_downlink_body"]["messages"]


def test_image_chain_parses_four_creations():
    msgs = parse_chain_response({"pull_singe_chain_downlink_body":
                                 {"messages": _image_messages()}})
    assert len(msgs) == 2
    bot = next(m for m in msgs if m.user_type == 2)
    creations = [c for c in bot.creations if c.type == TYPE_IMAGE]
    assert len(creations) == 4, "Seedream 4.5 默认一组 4 张"
    first = creations[0]
    assert first.image is not None
    im = first.image
    assert im.is_finished, "实抓为成品 status=2"
    assert im.width == 2048 and im.height == 2048
    assert im.model == "Seedream 4.5", "placeholder.description 自报模型"
    assert im.ratio == "1:1"
    assert im.request_id, "一组共享 request_id"
    assert {c.image.request_id for c in creations} == {im.request_id}
    assert im.urls.get("ori_raw"), "image_ori_raw 存在"
    assert im.prompt.startswith("生成图片：")


def test_video_chain_parses_vod_urls():
    msgs = parse_chain_response({"pull_singe_chain_downlink_body":
                                 {"messages": _video_messages()}})
    bot = next(m for m in msgs if m.user_type == 2)
    vids = [c for c in bot.creations if c.type == TYPE_VIDEO]
    assert len(vids) == 1
    v = vids[0].video
    assert v is not None and v.is_finished, "实抓为成品 status=3"
    assert v.vid.startswith("v"), f"TOS vid 形态: {v.vid}"
    assert v.duration_s > 5.0
    assert v.definition == "1080p"
    assert v.play_url_1080p.startswith("http"), "base64 main_url 应解出直链"
    assert v.download_url.startswith("http")
    assert v.cover_url.startswith("http")


def test_loading_block_marks_generating():
    raw = [{"block_type": 10101, "block_id": "x",
            "content": {"loading_block": {"text": "正在创作", "scene": 1}},
            "is_finish": True}]
    m = parse_message({"message_id": 1, "user_type": 2,
                       "content": json.dumps(raw)})
    assert m.is_generating
    assert m.loading == ["正在创作"]


def test_double_encoded_content_is_required():
    # content 若已是 list 直接吃；str 必须 JSON；垃圾类型抛 TypeError
    assert parse_message({"message_id": 1, "user_type": 1, "content": []}).texts == []
    try:
        parse_message({"message_id": 1, "user_type": 1, "content": 123})
    except TypeError:
        pass
    else:  # pragma: no cover
        raise AssertionError("content=123 应抛 TypeError")
