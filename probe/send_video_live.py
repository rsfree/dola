#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实弹一发视频生成：真实发送 + SSE 全帧落盘 + FETCH_STREAM 续拉 + 轮询产物。

🔴 计费：消耗 2 个视频生成额度（免费档/日）。运行 = 用户已确认消耗。

用法：
  python probe/send_video_live.py --prompt "一只橘猫在草地上追蝴蝶，电影感" [--yes]

产物：
  probe/out_live/sse_sync.jsonl    /chat/completion 全帧
  probe/out_live/sse_async.jsonl   /chat/async/chunk_stream 全帧（若发生切换）
  probe/out_live/chain_final.json  终态消息链（creation_block）
  probe/out_live/video_raw.mp4     无水印成品（若成功）
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.upstream.dola import (DolaClient, DolaError, build_completion_body,
                               parse_chain_response)
from app.upstream.dola.models import TYPE_IMAGE, TYPE_VIDEO

OUT = pathlib.Path(__file__).resolve().parent / "out_live"
SKILL_VIDEO = 17


def dump_frame(fh, event: str, data: str, fid: str) -> None:
    fh.write(json.dumps({"id": fid, "event": event, "data": data},
                        ensure_ascii=False) + "\n")
    fh.flush()


def read_stream(client: DolaClient, cm, fh, phase: str) -> dict:
    """读一条 SSE 流到终态；发生 FETCH_STREAM 切换时返回切换信息。"""
    info: dict = {}
    with cm as resp:
        for event, data, fid in client.sse_frames(resp):
            dump_frame(fh, event, data, fid)
            if not data:
                continue
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            if event == "STREAM_ERROR" or payload.get("error_code"):
                raise DolaError(f"[{phase}] STREAM_ERROR {data[:200]}")
            # 事件数据可能在 event_data 字段（Bx 枚举：CMPL/FIN/ERR/CMD/FETCH_STREAM）
            inner = payload.get("event_data")
            ed = json.loads(inner) if isinstance(inner, str) else (inner or payload)
            etype = str(payload.get("event_type") or ed.get("event_type") or event)
            if "FETCH" in etype.upper() or (isinstance(ed, dict) and ed.get("fetch_key")):
                info["fetch"] = ed
                print(f"  [{phase}] FETCH_STREAM: {json.dumps(ed, ensure_ascii=False)[:200]}")
    return info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default="一只戴宇航员头盔的柴犬，皮克斯风格")
    ap.add_argument("--skill", type=int, default=17, help="3=图像 17=视频")
    ap.add_argument("--ratio", default="")
    ap.add_argument("--duration", default="")
    ap.add_argument("--yes", action="store_true", help="确认消耗生成额度")
    args = ap.parse_args()
    if not args.yes:
        sys.exit("🔴 计费动作：加 --yes 确认消耗视频额度")

    cookie = (pathlib.Path(__file__).parent / ".dola_cookie").read_text().strip()
    # 🔴 写侧地理围栏（710022003 country restricted）：国内直连被拒，必须走系统代理
    proxy = os.environ.get("DOLA_PROXY", "http://127.0.0.1:57890")
    client = DolaClient(cookie, proxy=proxy)
    print("proxy:", proxy)
    if not OUT.exists():
        OUT.mkdir(parents=True)   # 🔴 shim 的 mkdir 对已存在目录会抛 EEXIST，别裸调

    rl = client.check_send_rate_limit()
    print("rate_limit:", json.dumps(rl, ensure_ascii=False))

    if args.skill == 3:
        prefix = "生成图片：%s"
        ap_ = {"input_box_content": {"user_input_content": args.prompt,
                                     "reply_message_format": prefix}}
    else:
        ap_ = {"model": "ic_mini",
               "input_box_content": {"user_input_content": args.prompt,
                                     "reply_message_format": "生成视频：%s"}}
        if args.duration:
            ap_["duration"] = int(args.duration)
    body = build_completion_body(prompt=args.prompt, skill_type=args.skill,
                                 ability_param=ap_)
    (OUT / "request_body.json").write_text(
        json.dumps(body, ensure_ascii=False, indent=1))
    print("request ->", OUT / "request_body.json")

    t0 = time.time()
    before = {c.get("conversation_id") for c in client.recent_conv()}
    fetch = None
    with (OUT / "sse_sync.jsonl").open("w") as fh:
        try:
            info = read_stream(client, client.send_completion(body, dry_run=False),
                               fh, "sync")
            fetch = info.get("fetch")
        except DolaError as e:
            print("SYNC ERROR:", e)

    # 🔴 轮询要用服务端数字会话 id（本地 UUID 只是客户端标识，712010202 实抓）
    conv_id = None
    for _ in range(10):
        time.sleep(2)
        for c in client.recent_conv():
            if c.get("conversation_id") not in before:
                conv_id = c.get("conversation_id")
                break
        if conv_id:
            break
    print("server conv_id:", conv_id)

    if fetch:
        fk = fetch.get("fetch_key") or fetch.get("task_id")
        scene = int(fetch.get("append_scene") or 0)
        print(f"handoff -> async task_id={fk} scene={scene}")
        with (OUT / "sse_async.jsonl").open("w") as fh:
            try:
                read_stream(client, client.async_chunk_stream(fk, scene), fh, "async")
            except DolaError as e:
                print("ASYNC ERROR:", e)

    # 轮询消息链到视频成品（上限 8 分钟）
    if not conv_id:
        print("未发现新会话——发送可能被拒，见 sse_sync.jsonl")
        client.close()
        return
    print("polling chain for", conv_id)
    final = None
    for i in range(96):
        time.sleep(5)
        try:
            raw = client.chain_single_raw(conv_id)
        except DolaError as e:
            print("  poll err:", str(e)[:80]); continue
        msgs = parse_chain_response(raw)
        want = TYPE_VIDEO if args.skill == 17 else TYPE_IMAGE
        arts = [c for m in msgs for c in m.creations if c.type == want]
        if arts:
            a = arts[0]
            done = a.video.is_finished if want == TYPE_VIDEO else a.image.is_finished
            st = a.video.status if want == TYPE_VIDEO else a.image.status
            print(f"  t+{time.time()-t0:.0f}s status={st}")
            if done:
                final = raw
                (OUT / "chain_final.json").write_text(json.dumps(raw, ensure_ascii=False))
                import httpx
                url = a.video.best_url if want == TYPE_VIDEO else a.image.raw_url
                name = "video_raw.mp4" if want == TYPE_VIDEO else "image_raw.jpg"
                with httpx.Client(trust_env=False, timeout=120, follow_redirects=True) as h:
                    r = h.get(url)
                    (OUT / name).write_bytes(r.content)
                print(f"DONE t+{time.time()-t0:.0f}s -> {OUT/name} "
                      f"({len(r.content)//1024}KB)")
                break
        else:
            print(f"  t+{time.time()-t0:.0f}s no creation yet")
    else:
        print("TIMEOUT 8min，终态链存于 chain_final.json（若产生）")
        try:
            (OUT / "chain_final.json").write_text(
                json.dumps(client.chain_single_raw(conv_id), ensure_ascii=False))
        except Exception as e:
            print("chain dump failed:", e)
    client.close()


if __name__ == "__main__":
    main()
