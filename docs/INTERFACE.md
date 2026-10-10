# dola-service 对外契约（冻结）

> 本文件是**唯一的对外契约真相**。改动 = 破坏调用方，必须同步 `tests/`。
> 上游侧的字段与错误码在 `docs/upstream/dola-api.md`。

---

## 0. 端点

| 方法 | 路径 | 鉴权 | 状态码 | 用途 |
|---|---|---|---|---|
| `POST` | `/v1/images/generations` | 🔒 | `200` | **同步**出图（创建+轮询合并，≤`IMAGE_POLL_TIMEOUT`） |
| `POST` | `/async/v1/images/generations` | 🔒 | `202` | 受理，只回 `task_id` |
| `GET` | `/async/v1/images/generations/{task_id}` | 🔒 | `200`/`404` | 查询（不存在/非属主一律 404） |
| `GET` | `/async/v1/images/generations` | 🔒 | `200` | 本 Key 的任务列表 |
| `DELETE` | `/async/v1/images/generations/{task_id}` | 🔒 | `200`/`400` | 删除**已终态**任务 |
| `POST` | `/api/v3/contents/generations/tasks` | 🔒 | `200` | **视频唯一入口**：火山方舟契约 |
| `GET` | `/api/v3/contents/generations/tasks/{id}` | 🔒 | `200`/`404` | 方舟契约查询 |
| `GET` | `/v1/models` | 🔓 | `200` | 能力清单（只此一条免鉴权） |
| `GET` | `/healthz` `/readyz` | 🔓 | 200/503 | 探活；readyz 会 ping 铸签 sidecar |

## 0.7 出口节点（egress nodes，对齐 grok2api `egress-nodes` 概念）

节点 = 命名的出口配置，账号通过 `"node": <id>` 绑定（账号直配 `"proxy"` 优先）。

| 端点 | 用途 |
|---|---|
| `GET /v1/nodes` | 节点列表（代理脱敏：只露 scheme://host:port + per_account 标记 + 最近实测出口 IP） |
| `GET /v1/nodes/{id}/test?account=<name>` | **实测出口 IP**（经该节点按账号解析的代理请求 ipify）。同节点换 account 名测得不同 IP ⇒ per-account 粘性生效 |

配置 `DOLA_NODES_FILE`：`[{"id":2,"name":"livetest-per-account-2090","proxy":"http://{account}:<pass>@gw:2090"}]`
—— 模板含 **`{account}`** 占位 ⇒ 按账号粘性（网关按用户名给固定 IP，102 账号共用一节点各得一 IP）；
不含 ⇒ 静态共享出口。示例见 `nodes.example.json`。

## 0.8 账号池与 IP 隔离（参照 grok.1task.cn 形态）

每个上游账号（cookie）绑定独立出口代理 IP，实现账号隔离：

| 语义 | 说明 |
|---|---|
| 配置 | `DOLA_ACCOUNTS_FILE` 指向 JSON：`[{"name","cookie","proxy"},...]`；或 `DOLA_ACCOUNTS` 环境变量同结构；或退化单账号 `DOLA_COOKIE`(+`DOLA_PROXY`) |
| 调度 | 默认健康账号轮询；`X-Account: <name>` 请求头显式点名 |
| **隔离** | 同一账号的发送+轮询恒走同一出口 IP（每账号常驻客户端）；**视频任务轮询与创建账号亲和**（conv 归账号可见，绝不换号） |
| 健康 | 上游 `712012001` ⇒ 账号标记 dead 自动摘除；额度错视为链路健康 |
| 可见性 | `GET /v1/accounts`（🔒）回账号快照；**代理凭据脱敏**（只露 host:port） |
| 点名规则 | 点名不存在/已死账号 → `400` 明确报错，**绝不静默换号**（会话不可见） |

## 1. 模型

| id | 类 | 上游 | 备注 |
|---|---|---|---|
| `dola-seedream-4.5` | 图像 | Seedream 4.5（默认档） | 已验证 |
| `dola-seedance-1-0` | 视频 | Dreamina Seedance 1.0（`ic_mini`，10s 1080p） | 已验证 |

🔴 只登记**实抓验证过**的模型键。Seedream 5.0 Pro / Seedance 2.x 的上游内部键
未实抓 —— 不猜（猜错=710020202），待抓包后追加。

## 2. 请求/响应示例

```bash
# 同步出图
curl -X POST :8490/v1/images/generations \
  -H "Authorization: Bearer $KEY" -H 'content-type: application/json' \
  -d '{"prompt":"一只戴宇航员头盔的柴犬","model":"dola-seedream-4.5","ratio":"1:1"}'
# 200 -> {"created":..., "data":[{"url":"https://p16-flow-image-sign...","size":"2048x2048",
#         "model":"Seedream 4.5","watermark":false}], "conversation_id":"..."}

# 视频（方舟契约）
curl -X POST :8490/api/v3/contents/generations/tasks \
  -H "Authorization: Bearer $KEY" -H 'content-type: application/json' \
  -d '{"model":"dola-seedance-1-0","content":[{"type":"text","text":"一只柴犬在雪地奔跑"}]}'
# 200 -> {"id":"<task_id>","model":"dola-seedance-1-0","status":"queued"}
# GET 同路径/{id} -> {"id","model","status":"queued|running|succeeded|failed",
#                     "content":{"video_url":"..."},"error":"..."}
```

产物 URL 一律取**无水印变体**（图像 `image_ori_raw`，视频 VOD `lr=unwatermarked`），
字段名带 `watermark: false` 留痕。

## 3. 错误信封

```json
{"error": {"type": "quota_exceeded", "message": "今天的生成次数已经达到上限...",
           "upstream": {}}}
```

| type | HTTP | 重试语义 |
|---|---|---|
| `invalid_parameter` | 400 | 改参数 |
| `auth_error` | 401 | 换调用方 key |
| `quota_exceeded` | 429 | **重试无效**（上游日额度） |
| `upstream_auth` | 502 | **换 DOLA_COOKIE**（sessionid 过期） |
| `upstream_risk` | 502 | 重铸签名再试一次（服务内已自动） |
| `upstream_unavailable` | 502 | 可退避重试（地理/网关） |
| `skill_mismatch` | 500 | 上游按错误技能出产物（内部告警项） |
| `generation_timeout` | 500 | 轮询超时，产物可能稍后可用（查 conversation_id） |

## 4. 部署要点

| 变量 | 必须 | 说明 |
|---|---|---|
| `DOLA_COOKIE` | ✅ | 上游 cookie（最小=sessionid 单键）；`712012001` 出现=换新（60 天硬期限） |
| `SIGNER_URL` | ✅ | 铸签 sidecar 地址（写路径必需） |
| `DOLA_PROXY` | 国内✅ | 写路径地理围栏（710022003）；读侧不需要 |
| `API_KEYS` | | 🔴 **默认 = Bearer 透传**：key 即调用方身份（HMAC 指纹→任务归属），服务不维护账号体系；`API_KEYS` 不配就是透传（任意非空 Bearer 接受，启动打 WARNING）。配了才切白名单模式 |
| `DB_PATH` | | sqlite 任务库（默认 `data/dola.sqlite3`） |

签名 sidecar：`signer/server.js`（Node 22 + puppeteer-core + Chrome），环境
`CHROME_PATH` / `DOLA_COOKIE` / `PROXY` / `PORT=8491`。

## 5. 已验证（2026-10-10）

- 全链路金丝雀（视频额度 0 场景）：铸签→签名发送→地理/鉴权/风控三道门→技能路由→
  额度检测→任务终态落库，全通
- a_bogus TTL ≥ 5min；同 body 重放幂等（`local_message_id` 去重）
- 图像同步链路（真实出图 4 张，`image_ori_raw` 无水印）
