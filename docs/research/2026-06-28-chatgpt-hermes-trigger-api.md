# 2026-06-28 ChatGPT Workspace Agent hermes 后端 API 调研

> 调研对象：ChatGPT Workspace Agent 的「自动化 / 调度」后端接口，以及 agent run 内容取回的可能性。
> 方法：本机只读探针（`/tmp/hermes_probe*.py`）+ 用户提供的前端抓包 + OpenAI 公开文档。
> 认证凭据均来自用户本人账号（Business，usage-based），未落盘、未入仓。

## 0. 背景与动机

- 本仓 `workspace-agent-relay-mcp` 的存在理由：公开 trigger API「请求即结束、无法取回结果」，relay 用 callback MCP + dashboard 补这个缺口。
- 用户账号在 chat 前端达到消息限额（无法发新消息），但发现 trigger API / 调度触发仍可用 → 想确认：
  1. agent access token 能否调 hermes 调度/run_now 接口？
  2. 若只能用浏览器登录态，本地化可行性多高？
  3. **能否把 agent run 的对话内容取回来？**（甚至绕过 chat UI 限额继续用 agent）

## 1. 两个 API 面（决定性结论）

| 维度 | 面 A：公开 trigger API | 面 B：内部 hermes / backend-api |
|---|---|---|
| Host | `api.chatgpt.com` | `chatgpt.com` |
| 路径 | `/v1/workspace_agents/{agtch_}/trigger` | `/backend-api/hermes/agent/{agt_}/...`、`/backend-api/conversation/{id}` |
| 认证 | **agent access token**（Bearer，per-agent） | **用户 session JWT + cookies + `chatgpt-account-id`**（owner 校验） |
| 能力 | `POST /trigger`，202，不返回 run id / 结果 | triggers CRUD/PATCH/run_now、conversations 列表、**对话内容 retrieval** |
| 调度 | 无（官方：schedule 只在 agent builder UI） | 有（SCHEDULE trigger + run_now） |
| 公开文档 | 有（developers.openai.com/workspace-agents/trigger-runs） | 无（内部接口，逆向） |

**认证结论（已实测确证）：**

- access token 调 hermes → `401 rejected_by_access_enforcement / no_matching_rule`：token 被网关识别为凭证，但 hermes 没有「接受 agent access token」的规则。
- access token 仍有效（排除失效混淆）：用 access token `POST` 公开 trigger 但故意缺必填字段 `input` → `400 body.input Field required`（走到请求体校验、未 401、**未触发 run**）。
- 浏览器 session（cookies + `/api/auth/session` 刷出的 JWT）调 hermes → 200。
- 浏览器 session 调 `/backend-api/conversation/{id}` → 200 + 完整消息树。

> 即：**hermes 调度/run_now 与对话内容取回都只能用浏览器 session，access token 只能做公开 trigger。**

## 2. 已发现端点清单（实测）

| 端点 | 方法 | auth | 实测状态 | 用途 / 备注 |
|---|---|---|---|---|
| `api.chatgpt.com/v1/workspace_agents/{agtch_}/trigger` | POST | access token | 202 | 公开触发，fire-and-forget，不返回 run id |
| `/backend-api/hermes/agent/{agt}/triggers` | GET | session | 200 | 列 trigger；`?scope=owned\|all_accessible`（只这两个枚举） |
| `/backend-api/hermes/agent/{agt}/triggers/{id}` | PATCH | session | 用户已用 | upsert trigger（type=SCHEDULE/API 等） |
| `/backend-api/hermes/agent/{agt}/triggers/{id}` | GET | session | 405 | 单条 trigger 不可 GET（只 PATCH/DELETE） |
| `/backend-api/hermes/agent/{agt}/triggers/{id}/run_now` | POST | session | 用户已用 | 立即触发，返回 `{status:"dispatched", run_id, conversation_id, duration_ms}` |
| `/backend-api/hermes/agent/{agt}/conversations?limit=N` | GET | session | 200 | 列 agent 对话（`id, title, fiber_id, fiber_status, fiber_is_responding, invocation{type, is_scheduled}, cursor, scheduled`） |
| `/backend-api/conversation/{conv_id}` | GET | session | **200 + `mapping`** | **完整消息树（user/assistant/tool 节点 + content parts）** |
| `/api/auth/session` | GET | cookies | 200 | 用 session cookie 换 access token（JWT），无需 `cf_clearance` |

trigger 对象结构（`gpt_trigger`）：

```json
{
  "object": "gpt_trigger",
  "id": "<trigger_id>",
  "gpt_id": "agt_<agent_id>",
  "owner_user_id": "user-...__<account_id>",
  "trigger": {
    "type": "SCHEDULE" | "API" | ...,
    "enabled": true,
    "instructions": "查看电脑实时的 cpu/内存 资源占用情况",
    "channel_binding": {"type": "chatgpt"},
    "parent_trigger_id": null,
    "tz": "Asia/Shanghai",
    "rules": [{"freq":"hourly","hour":null,"minute":0,"byweekday":null,"bymonthday":null,"interval":1}]
  },
  "created_at": "...", "updated_at": "..."
}
```

conversations list item 结构：

```json
{
  "id": "<conversation_uuid>",
  "title": "橘子",
  "last_used_at": "...",
  "fiber_id": "<hex32>",
  "fiber_status": "completed",
  "fiber_is_responding": false,
  "invocation": {"type": "chatgpt" | "api", "is_scheduled": true}
}
```

`/backend-api/conversation/{id}` 返回顶层含 `mapping`（消息树）、`current_node`、`async_status` 等；`mapping` 是 `{message_id: {id, message:{author:{role}, content:{content_type, parts}, create_time, ...}, parent, children}}`。

## 3. 决定性证据

### 3.1 access token 不能调 hermes（探针 1/2）

- GET hermes collection（access token）→ `401 {"error":{"code":"no_matching_rule","type":"rejected_by_access_enforcement"}}`
- GET 公开 trigger（access token，GET）→ `401 security_policy_not_allowed`（公开面不允许 GET，只 POST）
- POST 公开 trigger 缺 `input`（access token）→ `400 invalid_request_error: body.input Field required` → **证实 token 有效**，且不触发 run
- GET hermes collection（无 auth）→ `403` + Cloudflare 挑战页
- GET hermes 单条 trigger（session）→ `405 Method Not Allowed`（鉴权过，路径不支持 GET）
- GET hermes collection（session）→ **200** + 真实 trigger 列表

### 3.2 对话内容可取回（探针 3/4，核心发现）

对一条已完成的 scheduled run（`conversation_id=6a407aa0-...`，`is_scheduled=true`，`fiber_status=completed`）：

- `/backend-api/hermes/agent/{agt}/conversations/{conv}` 及 `/messages`、`/stream`、`/fiber`、`fibers/{fiber}` 等 agent-scoped 路径 → **全 404**（hermes 不给内容，只给列表元数据）。
- `/backend-api/conversation/{conv_id}`（标准 chat 端点，session 鉴权）→ **200**，`mapping` 4 节点：
  - `[user]` 查看电脑实时的 cpu/内存 资源占用情况
  - `[assistant]` `{"agent_id":"agt_...","message":"查看电脑实时的 cpu/内存 资源占用情况"}`（agent 路由/echo）
  - `[assistant]` 当前电脑资源快照，时间 `2026-06-28 09:37:32` … CPU `31.55%` 用户态 / 内存 `15G` 已用 …

**结论：agent run 的完整对话内容可经浏览器 session + `/backend-api/conversation/{id}` 取回。** 这正是本仓 relay 一直用 callback 机制去补的「取回结果」缺口的另一条路径。

> **公开资料交叉印证**：子代理 web 调研（见 §7）从公开源证实：①公开 API 无 readback 是 OpenAI 官方承认的已知缺口（"agent response cannot currently be retrieved through the API… coming soon"）；②`GET /backend-api/conversation/{id}` 对**普通 chat** 能取回完整 `mapping`（0xdevalias gist / revChatGPT / export-chatgpt 等多源逆向印证）。但公开源对 **agent run 是否同样可达 `/backend-api/conversation/{id}`** 标记为「未公开逆向、unknown」——**本探针恰好实证了这条 unknown：YES，agent run 的 `conversation_id`（来自 hermes conversations list）直接命中 `/backend-api/conversation/{id}` 并返回含 agent 实际输出的 mapping。** 即本仓实测填补了公开源的那个空白。

### 3.3 浏览器登录态本地化可行性（实测，已修正）

**凭据分层与寿命（实测）：**

| 凭据 | 寿命 | 可否在 Python 侧自刷新 | 实测 |
|---|---|---|---|
| session JWT（`accessToken`） | 10 天 | 是——`/api/auth/session` 用 session cookie 换 | 200，2056 字符 |
| `__Secure-next-auth.session-token.0/.1` | 长会话 | 是——`/api/auth/session` 响应 Set-Cookie 轮换 | Set-Cookie 观测到 |
| `__cf_bm` | **~30 分钟** | **否**——`/api/auth/session` 与 conversations 端点都不 Set-Cookie 它 | 真实 70 分钟后 stale → 403 |
| `cf_clearance`（`.chatgpt.com`/`.openai.com`） | 观测到 ~1 年 expiry | — | **对 chatgpt.com 调用无效**（见下） |

**`__cf_bm` 是唯一门，cf_clearance 替代不了（单变量实测）：**

- 完整 jar，有/无 cf_clearance → 都 200（cf_clearance 既不需要也不增益）。
- **只去掉 `__cf_bm`**（保留 `__cflb`/`_cfuvid`/session），有/无 cf_clearance → **都 403**。
- 去掉全部 CF 短命 cookie + cf_clearance → 403。
- 真实侧证：首次 poller 运行在 cookie 导出 ~70 分钟后 403（`__cf_bm` stale）；换新导出（fresh `__cf_bm`）立即 200。

**修正后的可行性：**

| 场景 | 可行性 | 依据 |
|---|---|---|
| 一次性读回（导出后 30 分钟内跑一次） | **高** | 实测；触发用 access token（不需 session），读回时导出一次 cookie 跑一次 poller |
| 同机连续无人值守（纯 cookie 回放） | **低** | `__cf_bm` ~30 分钟到期且 Python 侧无法刷新；cf_clearance 无效 |
| 同机无人值守（CDP 驱动真实 Chrome） | **已实证（见 §9）** | Playwright `connect_over_cdp` 接独立 relay profile 的真实 Chrome；CF 信任真实 Chrome 指纹，`__cf_bm` 由浏览器自维；不依赖 opencli |
| 跨机 / 换 IP | 低 | `__cf_bm`/session 与浏览器会话+IP 绑定 |

**对 relay 的实操含义：** readback 不必连续无人值守。实用工作流是「access token 触发 run（不需 cookie）→ 想看结果时从浏览器导出一次 cookie → 30 分钟内跑一次 poller 取回 mapping」。连续轮询才需要重路径（真实浏览器续 `__cf_bm`）。

> `cf_clearance` 的 ~1 年 expiry 对本场景无用：它是按域的（`.chatgpt.com` 的只对 chatgpt.com；`.openai.com` 的只对 openai.com），且不替代 `__cf_bm`。`.openai.com` 的 cf_clearance 对 chatgpt.com backend-api 调用无关；是否能在 `api.openai.com`/`auth.openai.com` 上换到更稳的 readback 路径，未探（推测无关，JWT `aud=api.openai.com/v1` 但该面用 platform key / agent token，非 session）。

## 4. 对本仓 relay 的意义

### 4.1 现有缺口（已知）

调度触发的 run 不经过 `build_trigger_input`，不携带 `request_id`/`callback_token` → agent 醒来时无 relay 绑定 → relay 看不到该 run 的 plan/progress/result。

### 4.2 新可能：polling 取回（本次调研的核心价值）

用浏览器 session 做一条「轮询取回」链路，作为 callback 机制的补充/备选：

1. `GET /backend-api/hermes/agent/{agt}/conversations?limit=N` → 发现新 / `fiber_status` 变化的 conversation（拿 `id` 与 `fiber_status`）。
2. `GET /backend-api/conversation/{id}` → 取 `mapping` 消息树。
3. 把 mapping 翻译成 relay 的 plan/progress/result 事件（agent 的 tool calls / 步骤在树里以 `tool`/`assistant` 节点呈现）。

价值：
- 补**调度 run** 的可见性（不依赖 agent 主动 callback）。
- 可作为 callback 机制的**对账/兜底**（callback 丢包时从 conversation 重建）。
- 不需要改 agent 指令 / 不需要 `callback_token` 注入。

代价 / 约束：
- 依赖浏览器 session（本地优先单用户场景 OK；同机多日可行，跨机不稳）。
- 需做 conversation 增量同步（cursor 分页）+ mapping → relay event 的翻译层。
- 仍是 fire-and-forget 触发 → 轮询有延迟，非实时（除非找到 fiber 流式端点；本次探针的 `fibers/{id}/events` 等路径 404，待继续找）。

### 4.3 chat UI 限额与 trigger 的关系（用户动机）

- 实测：账号 chat 前端已达消息限额，但 `run_now`（session）与公开 trigger（access token）仍能成功 dispatch run。
- run 内容可经 session + `/backend-api/conversation/{id}` 取回。
- 即「UI 限额了，仍可 trigger + read back」在实测上成立。

**限额计量关系（子代理公开源调研，可信度分级）：**

存在**两套独立机制**，多数公开证据只覆盖其一：
- **交互式 chat 消息窗**（"resume at X"）= chat UI 的滚动窗口限流（Plus ~160/3h；Business instant 基本"无限"）。这是用户遇到的 UI 限额。
- **per-user 模型/功能计数器** = Business "advanced feature" 限额：agent mode **40 次/月/用户**（每次唯一 invocation 计一次，含 scheduled run；中间步骤不计）。

关键结论：
- **trigger API 是独立面**（官方定位 "outside the ChatGPT UI"，独立 credential + 异步队列），其文档错误表只有 `401/403/404/409`，**无 429 / usage_limit** → 交互式 chat 限额大概率**不阻断** trigger。但 OpenAI 未公开声明豁免。**Likely**。
- **scheduled run 与 on-demand/API run 计同一 per-user 计数器**（"each unique invocation, including scheduled runs, counts"）。**Confirmed（三方 FAQ 引用 OpenAI rate card）**。
- trigger API **无独立文档化的 RPM/RPD**；平台 429 是否适用于 Workspace Agent access token（与 platform API key 不同 credential 类）**Unverified**。
- `self_serve_business_usage_based` 是真实 plan 枚举（openai/codex PR #15934）。agent run 先吃 per-user included 限额，再吃 workspace credits（agent mode 30 credits/msg）；与 basic chat **分开计量**。2026-07-06 起对"在 ChatGPT 内调用的 agent run"按 token 计 credit，Slack 等外部触发继续免费——**API trigger 算"内部"还是"外部"未明确**。**Unverified gap**。
- per-user 计数器 / credit 具体数字来自三方 FAQ（Generous Work / ChatForest 引用 OpenAI rate card），非 developers.openai.com 主文档。

**ToS / 使用政策（重要，关乎用户动机）：**
- API / cron / scheduled 自动化触发 agent 是**官方支持**的用法（cookbook 明列 "scheduled job" / "weekly reporting" 用例）。
- 但 Services Agreement §3.3(h)/(i) 明确**禁止 "circumvent any rate limits or restrictions" / "violate or circumvent Usage Limits"**；Usage Policies 亦禁止 "bypass rate limits, restrictions, or safety measures"。
- 即：用 trigger API + readback 本身合规；但若**意图/效果是规避已触发的 usage 限额**，会触及 ToS。且 agent run 并非"免费绕过"——吃 agent mode 40/月 计数器与 credits，耗尽同样会被 block。

> 对本仓的结论：polling-readback 架构作为「补调度 run 可见性 / callback 兜底」是合规且有价值的方向；不要把它定位为"绕限额"工具。

### 4.4 mapping → relay event 翻译规则（MVP 实证）

`scripts/hermes_poller.py` 跑通，9 条 run 全部取回（落盘 `~/.workspace-agent-relay-mcp/hermes-poller/<conv_id>.json`）。mapping 结构足以重建 relay 事件，规则已摸清：

- **节点形态**：`mapping` 是 `user`/`assistant`（及 tool 用例里的 `tool`）消息节点，按 `create_time` 排序即得线性流。`status` ∈ `finished_successfully`/`in_progress`，`is_current` 标最新节点。
- **user 节点 = trigger input**：relay 触发的 run，user 消息正文就是 `build_trigger_input` 的产物，含 `request_id:`、`conversation_key:`、`callback_token:`、`relay_mcp:` 行 + completion contract / steer 措辞。**关键：可从 user 节点解析出 `request_id`/`conversation_key`，把 ChatGPT 侧 conversation 与 relay run 关联——无需 callback。**
- **assistant 首条 = 路由 echo**：`{"agent_id":"agt_...","message":"<user 输入原文>"}`，是 Workspace Agent 路由层回显，非真实输出，翻译时跳过/标 meta。
- **assistant 后续 = 真实输出/narration**：agent 的结果、进度叙述、甚至它对 `record_plan`/`ask_user`/`record_result` 调用的自述。**即 polling 路径能看到 agent 的 callback 动作意图，哪怕 callback 本身失败。**
- **steer 历史**：多轮 run 的 mapping 保留全部 follow-up（含每次轮换的新 `callback_token`），可重建 turn 边界。
- **`invocation.type`** 区分 `api`（公开 trigger）与 `chatgpt`+`is_scheduled`（hermes run_now/schedule），两类都可读 → polling 路径同时覆盖 relay 触发与调度触发。

**实操发现（直接关系用户痛点）**：run `6a3ff1fb` / `6a3f9c39` 里 assistant 报 `tool_not_configured` / "not configured for the Hermes Fiber backend"——relay MCP 工具（record_plan 等）虽在列表中但后端未真正配置，callback 失败。**polling-readback 在这种情况下仍能从 mapping 拿到 agent 做了什么、为何没回报**，正是 callback 机制的现实兜底价值。

**安全/隐私观察**：`build_trigger_input` 把明文 `callback_token` 放进 trigger `input`，因此 ChatGPT 侧 conversation log 保留了**明文 callback_token**（relay 侧只存哈希）。session 持有者可读历史 token。per-run、已轮换、run 多半已关闭，不可直接利用，但属数据留存点，记一笔。

## 5. agent id 映射

- `agt_6a3f36…`（GPT 对象 id，前缀脱敏）= 本仓 SQLite agent 2「小桔🍊」= `agtch_6a3f38…`（API trigger 通道 id，前缀脱敏）。
- `agt_` 与 `agtch_` 是同一 agent 的两套标识：前者用于 hermes/backend-api，后者用于公开 trigger API。
- hermes collection 返回的 `type=API` trigger 的 `gpt_id` 即 `agt_`，`id` 即 `agtch_`。

## 6. 未决项 / 下一步

- **schedule trigger 不在 collection list**：用户 PATCH 的 SCHEDULE trigger（`6a4079...`）在 `scope=owned` 与 `scope=all_accessible` 下都不可见（`scope=schedule` 不是合法枚举）。但它确实 fire 过（conversations 里有 `is_scheduled=true` 的记录）。推测 schedule 类 trigger 走另一个端点/过滤，或为临时态。待查。
- **fiber 流式/事件端点**：本次试探的 `fibers/{id}/events` 等 agent-scoped 路径全 404。公开源（alinr HAR 研究）证实 backend-api 有 realtime 通道 `GET /backend-api/celsius/ws/user` → `wss://ws.chatgpt.com`，以及 `/stream_status`——这两个是否承载 fiber liveness 待抓包验证；若可，polling 可升级为近实时。
- **mapping → relay event 翻译规则**：已由 `scripts/hermes_poller.py` MVP 实证，见 §4.4。下一步：写翻译层把 user 节点的 `request_id`/`conversation_key` 关联到 relay run，把 assistant 真实输出映射到 progress/result 事件；并对 tool 节点（notion-local-ops run）采样定形态。
- **access token 能否读 conversation**：推测不能（公开 API 只暴露 POST /trigger，子代理公开源印证），未探。
- **限额计量 / ToS**：子代理已查（见 §4.3）。trigger 与交互式 chat 限额大概率独立（无 429），但 agent run 吃 per-user agent-mode 计数器（40/月）+ credits；ToS 禁止规避 usage limit。未决：API trigger 在 2026-07-06 credit 计费下算"内部"还是"外部"未明确。
- **web 上的 hermes 逆向资料**：子代理已查（见 §7）。公开源对 hermes/fiber 零覆盖；`/backend-api/conversation/{id}` readback 对普通 chat 有公开逆向印证。

## 7. 公开资料印证（子代理 web 调研）

子代理仅查公开源、未对真实账号发起请求。结论按可信度分级：

**已印证（VERIFIED）**

- 公开 Workspace Agents API 只暴露 `POST /v1/workspace_agents/{agtch_}/trigger`，返回 202 无 body、无 run id；OpenAI 官方明确「agent response cannot currently be retrieved through the API… coming soon」——**本仓 relay 的存在理由站得住**。
- `GET /backend-api/conversation/{id}` 对**普通 chat** 返回完整 `mapping`（`content.parts` 全文），多源逆向印证（0xdevalias gist、revChatGPT、export-chatgpt、alinr HAR 研究）。需 session bearer + 设备头。
- `GET /backend-api/conversations?offset=&limit=`（limit≤100，`{items,total}`）列 chat 历史。
- `backend-api` 下有 realtime 通道 `GET /celsius/ws/user` → `wss://ws.chatgpt.com`，及 `/stream_status`。
- `backend-api/codex` 是确认存在的内部服务路径（Codex CLI 后端），带 `ChatGPT-Account-ID` 与 `x-openai-internal-codex-residency` 头 → **证明 backend-api 前置多个内部服务**（codex / conversations / sentinel / ecosystem / 推测含 hermes），OpenAI 有 `x-openai-internal-*` 路由头约定。
- 写操作类端点需 `sentinel/chat-requirements`（Turnstile + PoW）token。

**未印证（UNVERIFIED，仅本仓实测观察）**

- `hermes` 作为 OpenAI 内部服务名：公开源零覆盖（网上 "hermes" 命中的 NousResearch/hermes-agent 是无关的 Codex 客户端；"fiber" 命中的是 Cloudflare Agents SDK 的 durable-execution 原语，亦无关）。
- `/backend-api/hermes/agent/{agt}/triggers`、`/conversations` 及 `fiber_id`/`fiber_status`/`fiber_is_responding`/`invocation.{type,is_scheduled}` 字段：无公开文档或逆向。
- `fiber` 语义：结构上类比 OpenAI Assistants `Run`（queued→in_progress→completed 生命周期）与 Cloudflare fiber（durable run + status），是合理诠释，但 ChatGPT 内部语义未公开。

**关键交叉点**：子代理把「agent run 能否经 `/backend-api/conversation/{id}` 取回」列为公开未知的空白；**本仓探针实证填补了它（§3.2：YES）**。

## 8. 来源

- 实测探针：`/tmp/hermes_probe.py`、`/tmp/hermes_probe2.py`、`/tmp/hermes_probe3.py`、`/tmp/hermes_probe4.py`（本机 2026-06-28，只读 GET，凭据未落盘）。
- 用户提供前端抓包：PATCH trigger、POST run_now、GET triggers、GET conversations。
- OpenAI 公开文档：`developers.openai.com/workspace-agents/trigger-runs`、`/authentication`、`/cookbook/examples/chatgpt/workspace_agents/workspace-agents-api-trigger`。
- 公开逆向（子代理整理）：0xdevalias gist（`gist.github.com/0xdevalias/4e54bb28a02db5357ea4fa3a872fc5fc`）、acheong08/revChatGPT、brianjlacy/export-chatgpt、alinr HAR 研究（`alinr.com/experiments/chatgpt-har-architecture-conversation-data.html`）、gin337/ChatGPTReversed、NousResearch/hermes-agent issues（`backend-api/codex` + `x-openai-internal-codex-residency`）。
- 本仓代码：`src/workspace_agent_relay_mcp/trigger.py`、`api/validation.py`、`api/routes/runs.py`。

## 9. CDP readback 路径（2026-06-28 实证，最终可行，无 opencli 依赖）

> 这是 §3.3「同机无人值守（重路径）」的实证落地：用真实 Chrome 续 `__cf_bm`，但**不引入 opencli 依赖**，只用已装的 Playwright。

### 9.1 三条死路（已排除）

1. **纯 cookie 回放（urllib）**：`__cf_bm` ~30 min 到期、Python 侧不可刷新 → 30 分钟后 403（§3.3）。
2. **Playwright 自带 Chromium（headed/headless）**：被 Cloudflare 识破。headless 直接拿不到 session；**headed 即使手动点 CF 挑战也死循环**（CF 检测 CDP/自动化指纹，挑战永不通过）。`--disable-blink-features=AutomationControlled` 无用。结论：chatgpt.com 的 CF 不接受 Playwright Chromium，无论 headed。
3. **CDP-attach 到主 Chrome（默认 profile）**：Chrome 安全规则拒绝——日志原文 `DevTools remote debugging requires a non-default data directory. Specify this using --user-data-dir.`。即 `--remote-debugging-port` **只在非默认 user-data-dir 上生效**；显式传 `--user-data-dir=<主 profile 同路径>` 也被拒（Chrome 按路径值判默认）。主 profile 开不了调试端口。

### 9.2 可行路径：独立 relay profile + 真实 Chrome + CDP

- **独立 profile**：`~/.workspace-agent-relay-mcp/relay-chrome/`（非默认 data-dir → 调试端口允许）。
- **启动**：`open -n -a "Google Chrome" --args --user-data-dir=<relay> --remote-debugging-port=9223 '--remote-allow-origins=*'`。`open -n` 让 Chrome 由 LaunchServices 托管、脱离 shell 生命周期（`nohup &` 从非交互 shell 起会被 shell 退出带走，实测会死）。`--remote-allow-origins=*` 必需（Chrome M111+ 拒绝未授权 origin 的 CDP 连接）。
- **登录态来源**：从主 profile 拷三个文件到 relay profile——`Local State`（Keychain `Chrome Safe Storage` 解密引用）+ `Default/Cookies`（chatgpt session）+ `Default/Preferences`（profile 合法性）。**同一 Chrome app 的 Keychain 密钥跨 profile 共享**，故拷来的 `Cookies` 能被解密 → relay profile 直接是登录态，无需手动登录。**不碰 `Login Data`（密码库）。** 实测：拷完后 `/api/auth/session` 直接返回 JWT（account uuid 前缀脱敏）。
- **传输**：Playwright `connect_over_cdp("http://127.0.0.1:9223")` → 取 `browser.contexts[0]` → 找/开 chatgpt.com tab → 页内 `fetch('/backend-api/...')`（same-origin、credentials:include、真实 Chrome 指纹 → CF 放行、`__cf_bm` 浏览器自维）。
- **读哪个账号**：relay profile 登的是哪个就读哪个。要读另一 ChatGPT 账号：主 Chrome 切到目标账号后重拷 cookie。

### 9.3 实证结果（`scripts/hermes_poller_cdp.py`）

```
session ok: account=<redacted-uuid> jwt_len=2011
agents: [('agt_6a3e05c4...', ''), ('agt_6a3d42…', 'Fu')]
using agent=agt_6a3d42…
listed 10 runs → fetched mappings → 20 records saved to ~/.workspace-agent-relay-mcp/hermes-poller/
```

- Fu agent 10 条 run 全部取回，mapping 含 `request_id`/`conversation_key`/`callback_token`/tool 节点/assistant 真实输出（§4.4 翻译规则适用）。
- 落盘结构与 `hermes_poller.py`（urllib 版）一致：`{conversation_id, title, create_time, current_node, hermes_meta, messages}`。

### 9.4 与 opencli 路径的取舍

| 维度 | CDP 独立 profile（本节，无依赖） | opencli（扩展通道） |
|---|---|---|
| 额外依赖 | 仅 Playwright（已装） | opencli + daemon + 扩展 |
| 用哪个 Chrome | 独立 relay Chrome（常驻） | 主 Chrome（已登录） |
| CF | 真实 Chrome 放行 | 真实 Chrome 放行 |
| 登录 | 拷 cookie 免登录 / 一次性登录 | 主 Chrome 已登录 |
| 受默认 profile 端口规则限制 | 否（用非默认 data-dir） | 否（走 chrome.debugger 扩展 API） |

两者原理同（真实 Chrome + in-page fetch），区别只在「独立 profile + CDP 端口」vs「扩展通道」。本仓选 CDP 独立 profile 以守「无额外依赖」。

### 9.5 运维形态 / 约束

- relay Chrome 须常驻（带 `--user-data-port=9223` 那条 `open -n` 启动）；关了就重启。
- session cookie 由 `/api/auth/session` 自刷（每次 poller 跑都刷），~10 天不活动或被吊销才需重登。
- poller 不关 relay tab（避免关掉唯一 tab 连带关窗、打扰登录态）。
- 仍是轮询，非实时（fiber 流式端点仍 404，§6）。

### 9.6 相关脚本

- `scripts/hermes_poller_cdp.py`：CDP 版 readback（本节实证），含 `--interval` watch 循环 + 抓后自动翻译。
- `scripts/hermes_fetch.py`：共享 in-page fetch 客户端（`PWHermes` + `jwt_account`），transport 无关，被 cdp poller 复用。
- `scripts/hermes_translate.py`：mapping → relay 事件翻译层，按 `request_id` 关联 relay run，输出 `<cid>.events.json`（`source=polling`，不落盘明文 callback_token）。有单测 `tests/test_hermes_translate.py`。
- `scripts/hermes_poller.py`：urllib 版（§4.4，30 分钟窗口内可用）。
- `scripts/hermes_poller_pw.py`：已删除（Playwright 自带 Chromium 版，§9.1 死路 2；CF 过不了；可复用部分抽进 `hermes_fetch.py`）。
