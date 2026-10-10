#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发送体构建 —— 2026-10-10 实抓版（probe/out_live/real_send_body.json 为准）。

🔴 旧版按 fg.6a8234c1be.js 模块 pNo 的 {messages, completion_option,...} 结构拼，
   实发被上游 `710020202 common invalid param` 拒——pNo 的产物只是中间层，
   真正发出的信封是 {client_meta, messages, option, chat_ability, user_context, ext}。
   **别再从 chunk 静态推断发送体**，以本文件的实抓结构为唯一依据。
"""
from __future__ import annotations

import json
import time
import uuid

#: 创作技能的 chat bot（实抓固定值；图像技能发送时若不同，以实抓为准再补）
CHAT_BOT_ID = "7339470689562525703"

SKILL_IMAGE = 3
SKILL_VIDEO = 17

#: 🔴 技能路由真相（2026-10-10 实弹 diff 发现）：服务端按**文本前缀**路由技能——
#: 浏览器把 "生成视频：/生成图片：" 直接拼进 text_block.text（reply_message_format
#: 只是回显模板）。发裸文本 + ability_type=17 会被当图像生成（实弹踩过）。
SKILL_PREFIX = {SKILL_IMAGE: "生成图片：", SKILL_VIDEO: "生成视频："}


def _local_conv_id() -> str:
    # 实抓格式：local_<13 位毫秒级数字>（不是 uuid）
    return f"local_{int(time.time() * 1000)}"


def build_completion_body(*, prompt: str, skill_type: int,
                          ability_param: dict | None = None,
                          conversation_id: str = "") -> dict:
    """构建 /chat/completion 真实信封。

    - `prompt`：用户原文。文本块里会自动拼 SKILL_PREFIX 前缀（= 浏览器行为，
      服务端按前缀路由技能）。
    - `ability_param`：技能参数 dict（**双重编码成紧凑 JSON 字符串**，
      separators 与浏览器逐字对齐）。
      视频实抓：{"model":"ic_mini","duration":10,
                "input_box_content":{"user_input_content":prompt,
                                     "reply_message_format":"生成视频：%s"}}
    """
    lcid = _local_conv_id()
    lmid = str(uuid.uuid1())
    block_id = str(uuid.uuid4())
    prefix = SKILL_PREFIX.get(skill_type, "")
    prefixed = f"{prefix}{prompt}" if prefix else prompt
    if ability_param is None:
        if skill_type == SKILL_VIDEO:
            ability_param = {"model": "ic_mini", "duration": 10,
                             "input_box_content": {
                                 "user_input_content": prompt,
                                 "reply_message_format": f"{prefix}%s"}}
        else:  # 图像（❓ ability_param 未实抓过图像发送，按同构推断，待验）
            ability_param = {"input_box_content": {
                "user_input_content": prompt,
                "reply_message_format": f"{prefix}%s"}}
    now_ms = int(time.time() * 1000)
    return {
        "client_meta": {
            "local_conversation_id": lcid,
            "conversation_id": conversation_id,
            "bot_id": CHAT_BOT_ID,
            "last_section_id": "",
            "last_message_index": None,
            "local_permissions": [
                {"permission_name": p, "status": 3}
                for p in ("ACCESS_COARSE_LOCATION", "ACCESS_FINE_LOCATION",
                          "ACCESS_BACKGROUND_LOCATION")
            ],
        },
        "messages": [{
            "local_message_id": lmid,
            "content_block": [{
                "block_type": 10000,
                "content": {"text_block": {"text": prefixed, "icon_url": "",
                                           "icon_url_dark": "", "summary": ""},
                            "pc_event_block": ""},
                "block_id": block_id,
                "parent_id": "",
                "meta_info": [],
                "append_fields": [],
            }],
            "message_status": 0,
        }],
        "option": {
            "send_message_scene": "",
            "create_time_ms": now_ms,
            "collect_id": "",
            "is_audio": False,
            "answer_with_suggest": False,
            "tts_switch": False,
            "need_deep_think": 0,
            "click_clear_context": False,
            "from_suggest": False,
            "is_regen": False,
            "is_replace": False,
            "is_from_click_option": False,
            "is_from_click_softlink": False,
            "disable_sse_cache": False,
            "select_text_action": "",
            "is_select_text": False,
            "resend_for_regen": False,
            "scene_type": 0,
            "unique_key": str(uuid.uuid4()),
            "start_seq": 0,
            "need_create_conversation": not conversation_id,
            "conversation_init_option": {"need_ack_conversation": True},
            "regen_query_id": [],
            "edit_query_id": [],
            "regen_instruction": "",
            "no_replace_for_regen": False,
            "message_from": 0,
            "shared_app_name": "",
            "shared_app_id": "",
            "sse_recv_event_options": {"support_chunk_delta": True},
            "support_lazy_fetch_stream": True,
            "is_ai_playground": False,
            "is_old_user": False,
            "recovery_option": {"is_recovery": False,
                                "req_create_time_sec": now_ms // 1000,
                                "append_sse_event_scene": 0},
            "message_storage_type": 0,
            "related_deleted_message_ids": {},
            "connector_info_list": [],
            "model_config": {"model_item_key": "", "model_extra_params": {}},
            "aggregate_params": {"mention_skill_list": "[]",
                                 "mention_plugin_list": "[]",
                                 "mention_ext": "[{}]",
                                 "conversation_mode": "", "mode_id": "",
                                 "model_item_key": "", "agent_mode": "",
                                 "reasoning_effort": "", "provider_id": ""},
        },
        "chat_ability": {
            "ability_type": skill_type,
            # 🔴 紧凑序列化（separators）——与浏览器逐字对齐，别用默认空格风格
            "ability_param": json.dumps(ability_param, ensure_ascii=False,
                                        separators=(",", ":")),
        },
        "user_context": [],
        "ext": {"answer_with_suggest": "0", "sub_conv_firstmet_type": "1",
                "collection_id": "", "is_finish": "1",
                "conversation_init_option": "{\"need_ack_conversation\":true}",
                "commerce_credit_config_enable": "0"},
    }
