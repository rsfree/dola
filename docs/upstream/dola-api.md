# Dola (dola.com) 上游契约 —— 图像/视频生成

> 只记录**服务依赖的事实**及其**出处**。标 ❓ 的是**未取证**项 —— 不要把它们当结论用。
> 取证方式：真实浏览器抓包（bsk，登录态）+ 前端 chunk 静态分析（301 个 async chunk 全量下载）。
> 实测时间：2026-10-10。实测账号：free 套餐，region=TW。

站点：`https://www.dola.com`（字节豆包海外版，Cici 体系；CDN `sf-flow-web-cdn.ciciai.com`，
监控 `mcs-nontt.dola.com`）。产物名 Dola，模型自报 **Seedream 4.5**（图像）/ **Dreamina Seedance**（视频）。

---

## 0. 与 jimeng 的对照

| 维度 | jimeng（即梦） | dola |
|---|---|---|
| 形态 | 独立 AIGC 站，REST + 轮询 | **AI 聊天助手，生成走聊天 SSE 流** |
| 建任务 | `POST /mweb/v1/aigc_draft/generate` | `POST /chat/completion`（流式，无显式任务 id） |
| 取任务 | `POST /mweb/v1/get_history_by_ids` | 同一条 SSE 流 + `FETCH_STREAM` 事件切换 `POST /chat/async/chunk_stream` 续拉 |
| 鉴权 | cookie `sessionid` + md5 sign | cookie 会话 + **msToken + a_bogus**（mssdk SDK，query 参数） |
| 任务回执 | task.status 状态机 | 消息流 block（`block_type=2074 creation_block`） |
| 产物 | 图片直链（ImageX） | TOS 签名 URL（图片 2048²；视频走 VOD 系统 vid） |
| 上传 | ImageX 四段式 | ❓ `/alice/upload/auth_token` + `/alice/upload/file`（未走查） |

## 1. 鉴权

🔴 **最小凭据 = cookie 里的一个键 `sessionid`**（2026-10-10 最小集负对照，读侧全链实测）：

| 格 | cookie | recent_conv | chain_single |
|---|---|---|---|
| A | `sessionid` 单键 | ✓ | ✓ |
| B | `sessionid_ss` 单键（同值） | ✓ | ✓ |
| C | `sid_tt` 单键（同值） | ✓ | ✓ |
| D | `uid_tt` 单键 | ✗ `712012001` | — |
| G | 全量 32 键（对照） | ✓ | ✓ |

⇒ 与 jimeng 同构：**一个会话键走天下**，`ttwid`/`msToken`/设备指纹等 30 个键全部不参与鉴权。
`sid_guard` 值内嵌有效期：`<sid>|<签发秒>|5184000|<到期 GMT>` = **60 天硬期限**。
（写侧 `/chat/completion` 未用单键实测——计费动作；鉴权层与读侧同为 AGW 登录校验，
判定相同，第一次实发时顺手复核。）

## 1.1 请求公共形态

**公共 query**（几乎所有 `/alice/*` `/samantha/*` `/im/*` 端点共用）：

```
version_code=20800 & language=zh & device_platform=web & doubao_device_platform=web
& aid=495671 & real_aid=495671 & pkg_type=release_version
& device_id=<device> & web_id=<webid> & tea_uuid=<uuid>
& region=TW & sys_region=TW & samantha_web=1 & tz_name=Asia%2FShanghai
& use-olympus-account=1 & web_platform=browser & ...
```

**BFF 信封**（`/im/*` 族；出处：chain/single 实抓）：

```json
{"cmd":3100, "uplink_body":{...}, "sequence_id":"<uuid4>", "channel":2, "version":"1"}
```

响应对称：`{"cmd":..., "sequence_id":..., "downlink_body":{...}, "status_code":0, "status_desc":"OK"}`

**签名分层（2026-10-10 负对照实锤，`probe/negctl/` + `probe/dola_probe.py negctl` 可复现）**：

| 请求形态 | 结果 | 判定 |
|---|---|---|
| `/im/chain/single` content-type=`application/json`（缺 `encoding=utf-8`） | `712012002 不支持编码类型` | 信封层在鉴权**之前** |
| 正确 content-type，无 cookie | `712012001 登录校验不合法` | 鉴权层，**无签名报错** |
| `POST /chat/completion` 无 cookie **无 msToken/a_bogus** | **SSE 打开** → `STREAM_ERROR 710012001 login invalid` | 🔴 **网关不强制 a_bogus** |
| `GET /chat/completion` | 404 | POST-only |

⇒ **纯 HTTP + cookie 即可走通读写两路**，a_bogus 铸签**暂不需要**。

🔴 **地理围栏（实弹实抓）**：`/chat/completion` 对**出口 IP** 校验——国内直连返回
`{"code":710022003,"msg":"您所在的国家/地区不可用"}`（HTTP 200，不是 SSE），
**读侧 `/im/*` 不拦**。浏览器能生成 = 走了系统代理。⇒ 国内部署时写路径必须挂代理
（`DolaClient(proxy=...)`，本机实测 `http://127.0.0.1:57890`）。

🔴🔴 **风控第三层（实弹实抓，最硬的一道）**：过了网关+鉴权+地理后，`/chat/completion`
还有 **shark_admin 风控**（字节 Shark）。非浏览器请求被判定 bot，SSE 内返回
`STREAM_ERROR 710022004 "rate limited"`，decision=`{type:"verify", subtype:"slide",
from:"shark_admin"}`（带加密 detail blob）→ **要求滑块验证**。实测排除项：

| 尝试 | 结果 |
|---|---|
| 全套浏览器指纹头（sec-ch-ua/sec-fetch-*） | ❌ 仍滑块 |
| 完整 query（fp/msToken/region/tab_id） | ❌ 仍滑块 |
| curl_cffi impersonate=chrome（TLS 指纹） | ❌ 仍滑块 |

⇒ 差异只剩 **a_bogus（SDK 内部生成）与页面级行为信号**。三次被拦均未建任务（零消耗）。

**架构决断（v1 混合）**：读侧纯 HTTP（sessionid 单键，已全链验证）；写侧走**浏览器执行器**
（bsk/真实 Chrome，两次实弹成功）。

### 4.0.1 🎉 2026-10-10 深夜突破：a_bogus 就是钥匙，纯 HTTP 写已通

**零成本金丝雀实验**（视频额度 0/2 时发起视频请求，额度错=免费）：

1. 浏览器 fetch 钩子抓 body + bsk debug 抓**带 a_bogus 的签名 URL**（浏览器 UI 发视频，
   过风控、被额度错拒——"今天的生成次数已经达到上限"）
2. 纯 HTTP（curl_cffi chrome）**原样重放** 签名URL+body → **shark 放行**！
   活体 SSE 全流到手：`SSE_ACK`（conversation_id）→ `FULL_MSG_NOTIFY` →
   `DOWNLINK_CMD(310 chunk_update)` → `STREAM_MSG_NOTIFY` / `STREAM_CHUNK`
   （`patch_op` 增量补丁流，patch_type 1/2/111，tts_content 同步）→ bot 回额度提示

⇒ **结论：a_bogus 是 shark 的唯一决定性信号**（TLS 指纹/指纹头/msToken 全排除，
   msToken 一小时不轮换且浏览器与我们同值）。签名 URL+body 原样重放即过。
   v2 铸签路线确认可行，零副作用铸签配方：**bsk debug 规则 `mock` 拦截 mint URL**
   （SDK 签名后网络层被 mock 吞掉，不真发；签名 URL 从 debug requests 取）。
   **TTL 实测**：铸造后 **4-6 分钟仍有效**（二次重放得 SSE_ACK 而非滑块）；
   且同一 body 重放被服务端按 `local_message_id` **幂等去重**（返回同一 question_id，
   不新增消息）⇒ 适配器重试安全，铸签可池化、不必每请求现签。
⚠️ 字节风控可能动态开启校验（jimeng 有 `1014 ErrSign` 先例）—— 上线后监控；
   SSE 帧格式实抓：`id: 0` / `event: SSE_HEARTBEAT|STREAM_ERROR` / `data: {...}`。

## 2. 端点表（图像/视频生成链路）

| 用途 | 端点 | 计费 | 取证 |
|---|---|---|---|
| **发送生成** | `POST /chat/completion`（SSE） | 🔴 扣额度 | 实抓 n1628（图） |
| **异步续拉** | `POST /chat/async/chunk_stream`（SSE） | 免费 | 静态（sdk-shell） |
| 消息链 | `POST /im/chain/single`（cmd=3100） | 免费 | 实抓 n774/n2014 |
| 会话列表 | `POST /im/chain/recent_conv` | 免费 | 实抓 n255 |
| 会话批量 | `POST /im/conversation/batch_get` | 免费 | 实抓 |
| 发送频控 | `POST /im/message/send_rate_limit`（cmd=2260） | 免费 | 实抓（只回 is_limit，无额度） |
| 上传 token | `POST /alice/upload/auth_token` | 免费 | 静态 ❓ |
| 上传文件 | `POST /alice/upload/file` | 免费 | 静态 ❓ |
| 视频生成信息 | `POST /samantha/video/query_video_gen_info` | 免费 | 静态 ❓ |
| 播放信息 | `POST /samantha/video/get_play_info`、`/samantha/media/get_play_info` | 免费 | 静态 ❓ |
| 技能列表 | `POST /samantha/skill/list`、`/samantha/skill/pack` | 免费 | 静态 |

**读侧零签名**：`/im/*` 族实测（页面加载）未触发 mssdk（include 列表只有 `/alice` `/samantha`
`/passport` `/biz` `/chat/completion` `/chat/async/chunk_stream`；注意 `/im/chain/single` 以 `/im`
开头 —— 是否需要 a_bogus **❓ 未做裸 HTTP 对照**，但浏览器实抓它不带 msToken 参数的概率高）。

**端点全表**：896 个 `genBaseURL` 端点见 `probe/routes_registry.txt`。

## 3. 发送体（`/chat/completion` 的 body）—— 🔴 以实抓为准

**2026-10-10 实弹教训**：按 chunk 静态推断（pNo 模块的 `{messages, completion_option,...}`）
拼体实发被 `710020202 common invalid param` 拒——pNo 只是中间层，真正发出的信封完全不同。
最终用浏览器 fetch 钩子抓到真身（`probe/out_live/real_send_body.json`）。
**教训入册：发送体别从 chunk 推断，钩子实测一次最省。**

真实信封（代码实现 `app/upstream/dola/send_body.py`）：

```jsonc
{
  "client_meta": {
    "local_conversation_id": "local_<13位毫秒>",   // 不是 uuid！
    "conversation_id": "",                          // 新会话留空
    "bot_id": "7339470689562525703",                // 固定 chat bot
    "last_section_id": "", "last_message_index": null,
    "local_permissions": [ /* 3 个定位权限，status=3 */ ]
  },
  "messages": [{
    "local_message_id": "<uuid1>",
    "content_block": [{                             // 🔴 叫 content_block，不是 content_blocks_v2
      "block_type": 10000,
      "content": {"text_block": {"text": "<用户原文>", "icon_url": "",
                                 "icon_url_dark": "", "summary": ""},
                  "pc_event_block": ""},
      "block_id": "<uuid4>", "parent_id": "", "meta_info": [], "append_fields": []
    }],
    "message_status": 0
  }],
  "option": {
    "create_time_ms": <ms>, "need_create_conversation": true,
    "conversation_init_option": {"need_ack_conversation": true},
    "unique_key": "<uuid4>", "start_seq": 0,
    "recovery_option": {"is_recovery": false, "req_create_time_sec": <sec>},
    "sse_recv_event_options": {"support_chunk_delta": true},
    "support_lazy_fetch_stream": true
    /* 另有一批 false/空值字段，全量见 send_body.py */
  },
  "chat_ability": {                                // 🔴 技能入口在这
    "ability_type": 17,                            // 图像=3 视频=17
    "ability_param": "{\"model\":\"ic_mini\",\"duration\":10,\"input_box_content\":{\"user_input_content\":\"一只橘猫...\",\"reply_message_format\":\"生成视频：%s\"}}"
    // 双重编码；视频模型键：ic_mini=Seedance 1.0（其余档位键 ❓ 待更多实抓）
    // prompt 前缀（"生成视频："）由 reply_message_format 模板声明，客户端发原文
  },
  "user_context": [],
  "ext": {"answer_with_suggest": "0", "is_finish": "1",
          "sub_conv_firstmet_type": "1", "commerce_credit_config_enable": "0",
          "conversation_init_option": "{\"need_ack_conversation\":true}", ...}
}
```

## 4. SSE 流协议（响应侧）

出处：`s1-im-sdk-shell.4deca6ea8f.js`（状态机）+ `s2-chat-runtime`（流解析）+ 实抓现象。

- 响应 `content-type: text/event-stream`，事件信封 `{event_type, event_data}`。
- 事件类型（`Bx` 枚举）：`CMPL`（增量包）/ `FIN`（完成）/ `ERR`（错误）/ `CMD` / `FETCH_STREAM`。
- **FETCH_STREAM 切换**：长任务（视频必然，图像偶发）下发
  `{fetch_key, fetch_type: AsyncTask, msg_id, append_scene}`；
  客户端随即 `POST /chat/async/chunk_stream`，body：
  ```json
  {"task_id": "<fetch_key>", "seq_start": 0, "ext": {}, "append_scene": <scene>}
  ```
  （重连时 `need_snapshot` / `support_lazy_fetch_stream` 可选；`seq_start` 按 event_id 去重续传。）
- `log_id` 从响应头 `x-tt-logid` 取。
- 增量块结构见 §5 消息块。

## 5. 消息块（产物结构）

消息 `content` 是 **block 数组的 JSON 字符串**（双重编码）。实抓两种：

### 5.1 占位（生成中）

```json
[{"block_type":10101,"block_id":"...","content":{"loading_block":{"text":"正在创作","scene":1}},"is_finish":true}]
```

### 5.2 成品（图像，实抓 4 张/组）

```jsonc
[{"block_type":2074,"content":{"creation_block":{"creations":[
  {"type":1,                        // 1=图像, 2=视频
   "id":"40032473487644433",
   "gen_detail":{"task_type":1},    // 图像=1；视频=6（实抓）
   "can_publish":true,
   "image":{
     "key":"tos-mya-i-3rsxbfecgb/rc_gen_image/<hash>.jpeg",
     "image_thumb":  {"url":"https://p16-flow-image-sign.ibyteimg.com/...~tplv-...wm...", "width":384,"height":384},
     "image_ori":    {"url":"...", "width":2048,"height":2048},   // 带水印模板
     "image_ori_raw":{"url":"...", "width":2048,"height":2048},   // ❓ raw 疑似无水印（tplv 模板不同，未逐字节比对）
     "image_preview":{...}, "status":2,
     "request_id":"20261010174758E41E77C915E1D556A59D",           // 一组 4 张共享
     "gen_params":{"prompt":"生成图片：...","ratio":"1:1"},          // 服务端回显
     "placeholder":{"width":2048,"height":2048,"description":"Seedream 4.5"}  // 模型自报
   }}]}}]
```

- URL 主机：`p16-flow-image-sign.ibyteimg.com`（`p19-` 亦有）；签名参数
  `x-expires`（约 1 年）+ `x-signature`；`~tplv-<space>-...` 是 ImageX 处理模板
  （`wm` 后缀 = 水印变体）。
- **状态**：image.status=2（成品，实抓）；cover/video.status=3（视频成品，实抓）。

### 5.2.1 🔴 无水印取法（2026-10-10 下载目检实锤）

| 媒介 | 带水印 | **无水印** |
|---|---|---|
| 图像 | `image_ori`（tplv 模板带 `wm`，右下角 "Dola AI" 角标） | **`image_ori_raw`**（2048² 原图，目检无角标） |
| 视频 | `download_url`（URL 参数 `lr=cici_ai`） | **`video_model.video_list.video_1.main_url`**（base64 解码，`lr=unwatermarked` + `logo_type=unwatermarked`，1080p；抽帧目检无角标） |

代码里已内建优先级：`ImageArtifact.raw_url` 与 `VideoArtifact.best_url` 均优先无水印变体；
`probe/dola_probe.py fetch <conv_id>` 一条命令下载会话内全部成品。

### 5.3 成品（视频，实抓自历史会话"生成猫视频"）

```jsonc
{"type":2,"id":"1553993916160529","gen_detail":{"task_type":6},
 "video":{
   "vid":"v186a3gm000cdb50f27og65oqaa6u1jg",
   "cover":{"key":"tos-mya-p-50851/<hash>","image_thumb":{...},"image_preview":{...}},
   "status":3, "width":384,"height":216, "duration":10.042, "video_type":"mp4",
   "download_url":"http://v19-dola.dola.com/.../video/tos/mya/tos-mya-ve-50851/<hash>/?...&lr=cici_ai...",
   "video_model":"{\"status\":10,...,\"video_list\":{\"video_1\":{\"definition\":\"1080p\",
      \"vwidth\":1248,\"vheight\":704,\"codec_type\":\"bytevc1\",\"main_url\":\"<base64 url>\",...}}}"
 }}
```

- 走 **VOD 系统**（`vod-urls-mya.byteintlapi.com` fallback），main_url 是 **base64 编码的播放直链**。
- 存在 `lr=unwatermarked` 变体（`logo_type=unwatermarked`）⇒ **无水印播放链可达**。
- 用户请求 5s，实得 10.042s —— ⚠️ 时长不是硬承诺。

## 6. 模型与额度

### 6.1 模型（UI 菜单实测）

| 类 | 模型 | 标签 |
|---|---|---|
| 图像 | Seedream 5.0 Pro | 专业出图・**4 倍消耗** |
| 图像 | Seedream 4.5（默认） | 日常生成（1 倍） |
| 视频 | Dreamina Seedance 2.5 | 旗舰视频标杆・**5 倍消耗** |
| 视频 | Dreamina Seedance 2.0 Fast | 快速出片选择 |
| 视频 | Dreamina Seedance 1.0 | 基础视频 |

### 6.2 额度语义（实测证据）

- 视频：独立池。回执原话"本次将消耗 **2 个视频生成额度**…今日剩余 **2 个视频生成额度**"
  （免费档默认模型一条=2 额度/日）。
- 图像：回执未直接给出额度数（SSE 丢包未留存 ack 文本 ❓）。模型菜单按"倍"计价 ⇒
  存在倍率体系；"图片占用视频额度吗" —— **无实锤，倾向不占用**（回执措辞为"视频生成额度"专用名词）。
- `send_rate_limit` 只做频控（`is_limit`/`limit_time`），**不是额度接口**。
- 免费档 `subs_status: "free"`（subscription entry config）。

## 7. SkillType 枚举（chat.js 内 `f` 枚举）

```
2=WriteAssistant  3=ImageGeneration  4=Search  5=Translate  6=ReadPDF  7=ReadWebsite
8=DeepSearch  9=MusicAssistant  10=AcademicSearch  11=ExerciseAssistant  12=ReadMultiWebsites
13=CodeInterpreter  14=ReferenceAsk  15=VoiceCall  16=CodeAssistant  17=VideoGeneration
18=AiPPT  19=MediaUnderstandingByAsr  20=SearchEngine  25=SkillDeepResearch  26=SkillAiPodcast
27=CustomSkill  100+=DesExt*
```

## 8. 风险与未决

| # | 项 | 状态 |
|---|---|---|
| 1 | ~~a_bogus / msToken 逆向~~ | ✅ **已排除**：网关不强制（无凭据 POST 到达业务层报 login invalid）；监控动态开启 |
| 2 | ~~视频发送体实抓~~ | ✅ **已实弹**：浏览器 fetch 钩子拿到真身（§3），轮询+无水印下载全链纯 HTTP 闭环 |
| 2b | 图像发送的 ability_param（图像技能发送实抓） | ✅ 纯 HTTP 实发验证：`{"input_box_content":{user_input_content,reply_message_format},"ratio":"16:9"}` → 4×2732×1534（比例生效） |
| 2d | **图生图（外部上传图）** | ✅ **全链实测成功**（2048×2048 成片）：真实契约与静态推断完全不同——参考图走 **`messages[0]` 的 attachment 消息**（`block_type=10052` + `attachment_block.attachments[0].image.uri=<上传后的TOS key>`），与文本消息（`block_type=10000`，text 自带"生成图片："前缀）**并列两条 message**；图像 `ability_param` 为双层嵌套 `{"ability_param":{"model":"Seedream 4.5","input_box_content":{...}},"ability_type":1}`（模型键=显示名）。上传链 4/4 段全通（§11）。顶层 ext.ref_images 不生效（实弹踩过） |
| 2c | ~~纯 HTTP 写路径的风控穿透~~ | ✅ **已打通**：a_bogus 是 shark 唯一关键（§4.0.1）。剩余工程：把"浏览器铸签（mock 拦截）→ 纯 HTTP 发送"封装成自动流程，并测 a_bogus TTL |
| 6 | SSE 事件完整 schema | ✅ 已活体抓全：SSE_HEARTBEAT / SSE_ACK / FULL_MSG_NOTIFY / DOWNLINK_CMD(310) / STREAM_MSG_NOTIFY / STREAM_CHUNK(patch_op) / STREAM_ERROR / FIN |
| 3 | 上传链路（/alice/upload/auth_token → file → image_token） | ❓ 未走查；v1 适配器建议只收 image_token/资产 key |
| 4 | ~~image_ori_raw 是否真无水印~~ | ✅ **已排除**：下载目检无角标；视频 play 直链（lr=unwatermarked）抽帧同样无角标。见 §5.2.1 |
| 5 | ~~cookie 最小集~~ | ✅ **单键 `sessionid` 即可**（§1 矩阵实锤，32→1）；写侧未单键实测（同层推断，下次实发复核） |
| 5b | 地理围栏 | 🔴 写路径国内直连被拒（710022003），必须走代理；读侧不拦（§4） |
| 6 | SSE 事件完整 schema（event_id、CMPL 包内层结构） | 部分（流被 capture 丢弃，只有静态侧）；🔴 注意 geo 拦截时 HTTP 200 + JSON 体（非 SSE），客户端要按 content-type 分流 |
| 7 | 保活/重登 | `sid_guard` 内嵌 60 天硬期限（§1）；`GET /passport/token/beat/web/` 纯 HTTP 可调（200 success，不轮换 sessionid，即"心跳可用、续期未证"）；`712012001` 出现 = 换 cookie |

## 9. 取证产物索引（probe/）

- `bundles/chat.js`、`bundles/xe.js` —— 主包
- `bundles/async/` —— 301 个懒加载 chunk（发版后可 re-diff）
- `routes_registry.txt` —— 896 端点全表
- `chain_single_body.json` —— 视频历史会话消息链（视频任务卡）
- `chain_image_full.json` —— 图像生成会话消息链（图像任务卡 ×4）
- `negctl/` —— 无凭据负对照原始响应
- `dola_probe.py` —— 统一 CLI：`conversations` / `chain <id>` / `send-dry-run` / `negctl`

## 11. 上传链（外部图片 → image_token，图生图前置）

抓包来源：用户 DevTools 三段 curl（2026-10-10）。纯 HTTP 复刻 **3/4 段通**：

| 段 | 请求 | 状态 |
|---|---|---|
| ① 受理 | `POST /alice/resource/prepare_upload` body `{"tenant_id":"5","scene_id":"4","resource_type":2}`（走粘性代理过地理门，**无需 a_bogus**） | ✅ 返回全明文 STS（ak+sk+session_token，1h）+ service_id=`uo7y4d541q`（与 jimeng 同一 ImageX 服务）+ upload_host |
| ② Apply | `GET https://imagex-ap-southeast-1.bytevcloudapi.com/?Action=ApplyImageUpload&Version=2018-08-01&ServiceId=...&FileSize=&FileExtension=` AWS4 签名（region=`us-east-1`，service=`imagex`，SignedHeaders 仅 `x-amz-date;x-amz-security-token`；jimeng upload.py 签名器直接复用） | ✅ StoreInfos(Auth=SpaceKey JWT) + SessionKey |
| ③ init | `POST {UploadHosts[0]}/upload/v1/{StoreUri}?uploadmode=part&phase=init`，头 `Authorization=<SpaceKey>` + `X-Storage-U=<uid>` | ✅ uploadid |
| ④ transfer | `POST {UploadHost}/upload/v1/{StoreUri}?uploadid=<id>&part_number=1&phase=transfer`，**原始字节 body** + 头 `Content-CRC32: <crc>` + `Content-Disposition: attachment` | ✅ code 2000 |
| ⑤ finish | `POST ...?uploadmode=part&phase=finish&uploadid=<id>`，body = **纯文本** `1:<crc32>`（多段逗号分隔，如 `1:xx,2:yy`） | ✅ code 2000 |
| ⑥ Commit | `POST ?Action=CommitImageUpload`（AWS4 含 x-amz-content-sha256，body `{"SessionKey":...}`） | ✅ `UriStatus:2000`，`ImageUri` 即 image_token |

**上传链 4/4（6 步）全通**。完整实现见 §10 upload.py。`/alice/upload/auth_token` 为死端点（scene 全扫 710010202），受理走 `resource/prepare_upload`。

⚠️ 注意：`/alice/upload/auth_token` 是**死端点**（页面签名调用 scene 全扫也是 710010202），上传受理走的是 `resource/prepare_upload`。
💡 短路结论：**引用 dola 已有图做图生图不需要上传链**——`ext.ref_images` 直接填已生成图的 TOS key。

## 10. 代码产物（app/upstream/dola/）

- `models.py` —— 消息块解析（creation_block → Image/VideoArtifact；VOD base64 直链解码）。
  回归向量 = 实抓链两份，`pytest tests/test_models.py`（4 用例）。
- `client.py` —— BFF 信封、读侧端点、错误分类（DolaAuthError/DolaEnvelopeError）、
  `build_completion_body()` 写侧契约（dry_run 默认拦截真实发送）。
