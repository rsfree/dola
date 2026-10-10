#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dola 上游探针 CLI（读侧）。

用法：
  export DOLA_COOKIE='...'        # 浏览器"复制全部 cookie"，一行
  python probe/dola_probe.py conversations
  python probe/dola_probe.py chain <conversation_id>
  python probe/dola_probe.py send-dry-run --skill 3 --prompt '一只猫' [--ratio 1:1 --model seedream45]

零凭据负对照（免费）：
  python probe/dola_probe.py negctl
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.upstream.dola import (BASE, DolaAuthError, DolaClient, DolaError,
                               build_completion_body, chain_single_body,
                               common_query, envelope)
from app.upstream.dola.client import (PATH_CHAIN_SINGLE, PATH_COMPLETION, UA)

SKILL_IMAGE = 3
SKILL_VIDEO = 17


def cmd_conversations(client: DolaClient) -> None:
    convs = client.recent_conv()
    print(f"{len(convs)} conversations:")
    for c in convs:
        print(f"  {c.get('conversation_id')}  type={c.get('conversation_type')}  "
              f"title={ (c.get('title') or '')[:40] }")


def cmd_chain(client: DolaClient, conversation_id: str) -> None:
    msgs = client.chain_single(conversation_id)
    print(f"{len(msgs)} messages in {conversation_id}:")
    for m in msgs:
        tag = "USER" if m.user_type == 1 else "BOT"
        if m.texts:
            print(f"  [{tag} {m.message_id}] text: {' '.join(m.texts)[:80]}")
        if m.loading:
            print(f"  [{tag} {m.message_id}] loading: {m.loading}")
        for c in m.creations:
            kind = "image" if c.type == 1 else ("video" if c.type == 2 else f"type{c.type}")
            done = "✓" if c.is_finished else "…"
            print(f"  [{tag} {m.message_id}] creation({kind}){done} id={c.creation_id}")
            if c.image:
                print(f"      {c.image.model} {c.image.width}x{c.image.height} "
                      f"ratio={c.image.ratio} raw_url={ (c.image.raw_url or '')[:90] }")
            if c.video:
                print(f"      vid={c.video.vid} {c.video.duration_s}s "
                      f"{c.video.definition} best={ (c.video.best_url or '')[:90] }")


def cmd_send_dry_run(args) -> None:
    ap_ = {}
    if args.skill == 17:
        ap_ = {"model": args.model or "ic_mini",
               "input_box_content": {"user_input_content": args.prompt,
                                     "reply_message_format": "生成视频：%s"}}
        if args.ratio:
            ap_["ratio"] = args.ratio
    body = build_completion_body(prompt=args.prompt, skill_type=args.skill,
                                 ability_param=ap_ or None)
    print(json.dumps(body, ensure_ascii=False, indent=2))
    print("\n# 🔴 dry-run：以上为将发送的 body（未发）。input_skill 为双重编码字符串。")


def cmd_fetch(client: DolaClient, conversation_id: str, outdir: str) -> None:
    """下载会话内全部成品（**无水印优先**，2026-10-10 双实测）。

    - 图像：image_ori_raw（2048²，无水印）> image_ori（右下角 Dola AI 水印）
    - 视频：video_list.video_1.main_url base64 解码（lr=unwatermarked，1080p）
            > download_url（lr=cici_ai，带水印）
    """
    import pathlib
    import httpx
    out = pathlib.Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    with httpx.Client(trust_env=False, timeout=60, follow_redirects=True) as h:
        for m in client.chain_single(conversation_id):
            for c in m.creations:
                if c.image and c.image.is_finished:
                    url, name = c.image.raw_url, f"{c.creation_id}_raw.jpg"
                elif c.video and c.video.is_finished:
                    url, name = c.video.best_url, f"{c.creation_id}_raw.mp4"
                else:
                    continue
                p = out / name
                r = h.get(url)
                r.raise_for_status()
                p.write_bytes(r.content)
                n += 1
                print(f"  ✓ {name}  {len(r.content)//1024}KB")
    print(f"{n} artifacts -> {out}")


def cmd_negctl() -> None:
    """无凭据负对照（零成本），复现 docs §1 分层表。"""
    q = "&".join(f"{k}={v}" for k, v in common_query().items())
    with httpx.Client(trust_env=False, timeout=10,
                      headers={"user-agent": UA, "agw-js-conv": "str"}) as h:
        # 信封层：错 content-type
        r = h.post(f"{BASE}{PATH_CHAIN_SINGLE}?{q}",
                   content=json.dumps(chain_single_body("0")),
                   headers={"content-type": "application/json"})
        print("N1 错content-type       ->", json.loads(r.text).get("status_code"),
              json.loads(r.text).get("status_desc"))
        # 鉴权层：对 content-type，无 cookie
        r = h.post(f"{BASE}{PATH_CHAIN_SINGLE}?{q}",
                   content=json.dumps(chain_single_body("0")),
                   headers={"content-type": "application/json; encoding=utf-8"})
        d = json.loads(r.text)
        print("N2 无cookie读侧        ->", d.get("status_code"), d.get("status_desc"))
        # 写侧：无 cookie 无签名
        with h.stream("POST", f"{BASE}{PATH_COMPLETION}?{q}",
                      content=json.dumps({"messages": [], "completion_option": {}}),
                      headers={"content-type": "application/json; encoding=utf-8"}) as s:
            body = b"".join(s.iter_bytes()).decode()
        line = [ln for ln in body.splitlines() if "error_msg" in ln]
        print("N3 无cookie写侧(SSE)   ->", (line[0].strip() if line else body[:120]))
        print("   （SSE 能打开 = 网关不强制 a_bogus，2026-10-10 实测）")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("conversations")
    p_chain = sub.add_parser("chain")
    p_chain.add_argument("conversation_id")
    p_fetch = sub.add_parser("fetch")
    p_fetch.add_argument("conversation_id")
    p_fetch.add_argument("--out", default="probe/out_wm")
    p_send = sub.add_parser("send-dry-run")
    p_send.add_argument("--prompt", required=True)
    p_send.add_argument("--skill", type=int, default=SKILL_IMAGE)
    p_send.add_argument("--ratio", default="")
    p_send.add_argument("--model", default="")
    sub.add_parser("negctl")
    args = ap.parse_args()

    if args.cmd == "negctl":
        cmd_negctl()
        return
    if args.cmd == "send-dry-run":
        cmd_send_dry_run(args)
        return
    cookie = os.environ.get("DOLA_COOKIE", "").strip()
    if not cookie:
        sys.exit("需要环境变量 DOLA_COOKIE（浏览器复制全部 cookie）")
    client = DolaClient(cookie, device_id=os.environ.get("DOLA_DEVICE_ID", ""))
    try:
        if args.cmd == "conversations":
            cmd_conversations(client)
        elif args.cmd == "chain":
            cmd_chain(client, args.conversation_id)
        elif args.cmd == "fetch":
            cmd_fetch(client, args.conversation_id, args.out)
    except DolaAuthError as e:
        sys.exit(f"❌ {e} —— cookie 过期/缺失，换新凭据")
    except DolaError as e:
        sys.exit(f"❌ {e}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
