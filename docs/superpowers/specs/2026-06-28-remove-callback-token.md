# 砍掉 callback_token：改动计划

日期：2026-06-28
状态：已评审，执行中（分支 `remove-callback-token`）。

## 背景

`callback_token` 是 relay 给每个 run 随机生成、经 trigger input 投递给 agent、agent 回调时带回、relay 比对 SHA-256 哈希认证的「per-run 秘密凭证」。设计初衷（[2026-06-26 设计 spec](./2026-06-26-workspace-agent-relay-mcp-design.md)）列的威胁是「leaked callback token could allow writing to one open run」。

经多轮质询核实，在当前实际部署下该凭证**不防任何真实会发生的坏事**：

1. **防外人**：`/mcp` 与 `/api/*` 已由 OAuth/bearer 把门（`api/auth.py` 的 `APIBearerAuthMiddleware`），轮不到 callback_token。
2. **防串对话**：`conversation_key` 已校验（`_validate_callback_conn` 比对 `run["conversation_key"]`），是真正的防串对话机制。
3. **防串回合**：`request_id` 每 turn 一个，按它路由；新 turn 有新 `request_id`，旧 turn 回调路由不到新 turn。
4. **防 stale prompt**：agent 串行，读最新 trigger 用最新 `request_id`，不会回翻旧 token；notion-local-ops 进程级绑定残留窗口极小。
5. **回合收盘**：靠 `run.status in TERMINAL_STATUSES` 判定，token 只是顺带失效。

结论：`callback_token` 在「MCP 已认证 + 本地单用户 + agent 串行」的现实用法下是过度设计。**唯一靠 token 秘密性真正把门的地方是 `/internal/tool-trace`**——该端点不在 `/api/` 也不在 `/mcp`，HTTP 层无认证，完全靠 body 里的 `callback_token`。砍 token 必须先补这个洞。

## 决策（已锁定）

1. **`/internal/tool-trace` 替代认证**：复用 `WORKSPACE_AGENT_RELAY_AUTH_TOKEN` 作 shared bearer（`Authorization: Bearer <token>`）。notion-local-ops 侧经 env `NOTION_LOCAL_OPS_RELAY_TOKEN`（默认回退 `WORKSPACE_AGENT_RELAY_AUTH_TOKEN`）读取。少一个 env，同机部署天然共享。
2. **DB 迁移**：重建表方式删 `runs.callback_token_hash` 列（SQLite 不能直接 DROP COLUMN，用新建表 + INSERT SELECT + RENAME）。迁移前必须本地备份 `relay.sqlite`。
3. **steer 语义**：砍掉 token 轮换概念。steer = 同 `request_id` 再发一次 trigger + 追加 `user_message` 事件 + 状态机照旧（`needs_user` → `sent` 等）。不再有「rotate」动作。

## 威胁模型（重新确立）

| 通道 | 现状把门 | 砍 token 后 | 风险 |
|---|---|---|---|
| `/api/*`（dashboard） | OAuth/bearer | 不变 | 无 |
| `/mcp` 工具（record_*） | OAuth/bearer + callback_token | OAuth/bearer + `request_id` 路由 | 低 |
| `/internal/tool-trace` | **仅 callback_token** | shared bearer（`AUTH_TOKEN`） | 中→低 |

## 改动清单

### 后端 store — `src/workspace_agent_relay_mcp/store/relay_store.py`

- 删 `REDACTED_CALLBACK_TOKEN`、`_hash_token`、`_redact_callback_token`、`_redact_artifact_scalar`。
- `_validate_callback_conn`：去 `callback_token` 入参与哈希比对，只留 `request_id` 存在 + `conversation_key` 匹配 + run 非终态。删 error code `invalid_callback_token`。
- `_init_schema`：`runs` 表删 `callback_token_hash` 列；加 forward migration（重建表）。
- `create_run` / `steer_run` / `record_plan` / `record_progress` / `record_result` / `ask_user` / `record_tool_trace`：去 `callback_token` 入参与所有 `_redact_callback_token(...)` 调用。
- `_redact_run`：去掉对 `callback_token_hash` 的 pop。

### 后端 routes — `api/routes/runs.py`

- `create_run` / `steer_run`：去 `generate_callback_token()`、`build_trigger_input(callback_token=...)`、`store.create_run(callback_token=...)` / `steer_run(new_callback_token=...)`。

### 后端 routes — `api/routes/internal.py`

- `post_tool_trace`：删 body `callback_token` 必填校验。
- 新增：`/internal/*` 要求 `Authorization: Bearer <AUTH_TOKEN>`（`AUTH_TOKEN` 为空时该端点 503/禁用，避免裸奔）。
- `_TRACE_ERROR_STATUS`：删 `invalid_callback_token`。

### 后端 trigger — `trigger.py`

- 删 `generate_callback_token`。
- `build_trigger_input`：删 `callback_token` 入参与 header 行 `callback_token: ...`；首/续/steer 三档文案改写（见「三处口径同步」）。

### 后端 MCP — `server.py`

- `record_plan` / `record_progress` / `record_result` / `ask_user` 签名去 `callback_token` 参数与 `store.xxx(callback_token=...)`。
- `MCP_INSTRUCTIONS`：删「freshly rotated callback_token」表述。

### 后端 http_compat — `http_compat.py`

- `DEBUG_SECRET_KEY_PARTS`：删 `callback_token` 条目。

### 前端 — `frontend/src/`

- `api/client.ts` 注释改写（无字段变更）。`pnpm run build` 须零错误。

### 兄弟仓 — `notion-local-ops-mcp`（跨仓同步）

- `bind_relay_run` 签名去 `callback_token`；进程级 binding 不再存 token。
- POST `/internal/tool-trace` body 去 `callback_token`；改带 `Authorization: Bearer <NOTION_LOCAL_OPS_RELAY_TOKEN>`。
- 两侧必须同批部署，否则 trace 全部 401。

## 三处口径同步（AGENTS.md §2 强制）

`trigger.py` 的 `build_trigger_input` / `server.py` 的 `MCP_INSTRUCTIONS` / `docs/agent-instructions.md` 三处措辞必须一致：

- **Relay Mode 进入条件**：三字段（`request_id` + `conversation_key` + `callback_token`）→ 两字段（`request_id` + `conversation_key`）。
- **bind_relay_run**：「用 `request_id` 和 `callback_token`」→「用 `request_id`（和 `conversation_key`）」。
- **steer**：「same `request_id`, freshly rotated `callback_token`, 用新 token 回调」→「same `request_id`, 继续用同一个 `request_id` 回调」。
- **record_result**：「exact `request_id`, `conversation_key`, and `callback_token`」→「exact `request_id` and `conversation_key`」。

## DB 迁移

SQLite 不能 `DROP COLUMN`（3.35+ 虽支持但不保险）。用重建表：

1. `CREATE TABLE runs_new (...)` 不含 `callback_token_hash`。
2. `INSERT INTO runs_new SELECT <所有保留列> FROM runs`。
3. `DROP TABLE runs`。
4. `RENAME TABLE runs_new TO runs`。
5. 重建索引（若有）。

在 `_init_schema` 的 `run_migrations` 块旁加 `if "callback_token_hash" in cols:` 分支触发一次性迁移。**迁移前必须本地 `cp relay.sqlite relay.sqlite.bak-2026-06-28`**（`*.sqlite*` 不进 git，本地备份）。

## 测试

### 改写

- `test_relay_store.py`：所有 `callback_token` / redaction / hash / steer-rotate 相关用例改写为「靠 `request_id` + run 状态收盘」。
- `test_mcp_callbacks.py`：`test_record_progress_rejects_wrong_callback_token` → 改为「wrong `conversation_key` 被拒」或删除。
- `test_tool_trace.py`：token 校验用例 → 改为 shared bearer 头校验。
- `test_trigger_payload.py`：steer 用例断言「same `request_id`, no token」。
- `test_server_transport.py`：`test_debug_rpc_summary_redacts_callback_token_argument` 删除。
- `test_web_api.py`：去 token 相关断言。

### 新增

- `/internal/tool-trace`：无 bearer / 错 bearer → 401；对 bearer + 正确 `request_id` → 200；`AUTH_TOKEN` 未配置时端点禁用。
- DB 迁移：老库含 `callback_token_hash` → 升级后列消失、run 数据完整。
- steer 不再 rotate，同 `request_id` 仍能继续回调。

## 验证（AGENTS.md §4）

```bash
.venv/bin/python -m pytest tests/ -q   # 须全绿
cd frontend && pnpm run build          # 须零错误
```

端到端（须真实 Workspace Agent）：

1. 新 turn → `record_plan` → notion bind（无 token）→ tool trace 经 shared bearer 落 dashboard → `record_result(done)`。
2. 中途 steer → 同 `request_id` 继续回调成功。
3. 新 turn 自动 supersede 旧 turn → 旧 turn 回调被 `run_closed` 拒。
4. 拔掉 notion-local-ops 的 `RELAY_TOKEN` → trace 全 401，证明认证生效。

## 分阶段 rollout（每步独立可提交）

1. 后端 store + 测试绿。
2. 后端 routes（runs / internal）。
3. 后端 trigger + server（含三处口径同步的第 1、2 处）。
4. http_compat + 前端注释。
5. DB 迁移 + 迁移测试。
6. 兄弟仓 notion-local-ops-mcp 同步。
7. 第 3 处指令同步 `docs/agent-instructions.md` + 粘贴到 ChatGPT。
8. 端到端验证。

## 风险与回退

- **最大风险**：step 6 两侧不同步 → trace 全 401。缓解：同批部署；plan/progress/result 走 MCP 不受影响。
- **不可逆点**：DB 重建表迁移。动前 `cp` 快照；回退 = 恢复备份 + `git revert`。
- 分支 `remove-callback-token`，小步提交，每步可独立验证。

## 变更记录

- **2026-06-28**：初稿。评审结论：callback_token 在当前部署下不防真实威胁，仅 `/internal/tool-trace` 依赖其秘密性。锁定三项决策（shared bearer 复用 `AUTH_TOKEN` / 重建表迁移 / steer 砍 rotate）。列出分阶段改动与同步口径。
