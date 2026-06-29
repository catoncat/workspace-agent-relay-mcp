# Polling 并入 relay 事件流（callback + polling 统一渲染）

日期：2026-06-28
状态：已评审，执行中（分支 `remove-callback-token`）。

## 1. 背景

CDP-attach 轮询已能取回 agent 在 ChatGPT 侧的完整对话（`/backend-api/conversation/{id}`）。验证（见 `docs/research/2026-06-28-chatgpt-hermes-trigger-api.md` §9）确认 polling 与 callback 覆盖**两个互不覆盖的平面**：

| run | callback 本地工具 trace（run_command/read_text/git_status） | 对话 tool 节点 |
|---|---|---|
| 58 | 49 | 0 |
| 13 | 37 | 0 |
| 69 | 5 | 2（均为 dalle 生图，非本地命令） |

- **callback = 本地执行面**：notion-local-ops 镜像的本地工具调用（从不出现在对话 mapping 里）+ 结构化 plan/result。
- **对话 = 云端可见面**：agent 的可见消息（推理/解释/求助）+ ChatGPT 原生工具（生图/code/web）。

结论：polling 不是 callback 的替代，而是补 cloud-side 视角。两者并集才完整。"直接解析显示对话"会丢掉本地执行（relay 的核心），所以仍需 merge。

## 2. 目标

- polling 产出的内容**映射到现有 event_type**，UI 零改、无来源标签（用户要求：UI 不关心来源）。
- 统一时间线：callback 事件 + polling 事件按 `created_at` 合并；唯一去重是终态（callback `result` 优先）。
- 幂等：poller 周期重跑不产生重复事件。
- 实时：poller 写入后 dashboard SSE 能推到合并视图。

## 3. 非目标

- 不改 agent 协议（`trigger.py` / `MCP_INSTRUCTIONS` / `docs/agent-instructions.md` 三处口径不变）。
- 不兼容旧 `callback_token` header（已随 `remove-callback-token` 移除）。
- 不把 polling 事件喂给 `get_run_context`（agent 不需要看自己说过的话）。

## 4. 数据模型

`events` 表加一列 + 一个部分唯一索引（仅约束 polling 事件）：

```sql
ALTER TABLE events ADD COLUMN source_key TEXT;  -- NULL=callback, <node_id>=polling
CREATE UNIQUE INDEX idx_events_polling_key
  ON events(run_id, source_key) WHERE source_key IS NOT NULL;
```

- callback 事件 `source_key = NULL`，不进索引，不受约束。
- polling 事件 `source_key = <ChatGPT mapping node_id>`，`(run_id, source_key)` 唯一 → `INSERT OR IGNORE` 幂等。
- `source_key IS NOT NULL` 即"polling 来源"标识，不需要额外 `source` 列。

## 5. 事件映射（polling → 现有 event_type）

| 对话节点 | 映射 | payload |
|---|---|---|
| agent 可见消息（非 echo） | `progress`（markdown=原文） | `{"polling": true}` |
| 云端 tool 节点（生图/code） | `progress`（trace 行） | `{"trace": true, "tool": <name>, "polling": true}` |
| 对话全局最后一条 agent 消息（fiber_status=completed） | `result`（合成） | `{"status": "done", "polling": true}` |
| user 节点 / agent echo | 跳过 | — |

- `result` 仅在 `fiber_status=="completed"` 时合成；run 仍在进行时（`in_progress`/responding）不合成，等下一轮 poll。
- 合成的 `result` 在读取端去重：若该 run 已有 callback `result`，丢弃所有 polling `result`。
- `created_at` = 消息 `create_time`（float epoch）转 ISO（`datetime.fromtimestamp(ct, UTC).isoformat()`），与 callback 事件同格式排序。
- `request_id` 列填该 run 的 `request_id`（保持一致）。

## 6. 读取端 merge（`list_events_merged`）

```
callback = events WHERE run_id=? AND source_key IS NULL
polling  = events WHERE run_id=? AND source_key IS NOT NULL
if any(e.event_type=='result' for e in callback):
    polling = [e for e in polling if e.event_type != 'result']
merged = (callback + polling) ORDER BY created_at, id
```

- `_run_detail` 与 `_notify_run` 改用 `list_events_merged`（dashboard + SSE 拿到合并视图）。
- `list_events`（callback-only）保留，供 `get_run_context`（agent 自身上下文）。

## 7. 写入端（单一写者 = relay server）

poller 是独立进程，**不直写 SQLite**（避免跨进程锁）。poller translate 后 POST 到新 internal 端点，由 server 进程的 store 实例写入（单写者，无并发）。

### 7.1 internal 端点

```
POST /internal/runs/{run_id:int}/polling-events
Authorization: Bearer <WORKSPACE_AGENT_RELAY_AUTH_TOKEN>
Body: { "events": [
  {"source_key": "<node_id>", "event_type": "progress"|"result",
   "title": str|null, "markdown": str|null, "payload": {...}, "create_time": float}
]}
```

- 复用 `InternalBearerAuthMiddleware`（shared bearer，与 `/internal/tool-trace` 同）。
- server 调 `store.record_polling_events(run_id, events)` → 幂等 `INSERT OR IGNORE` → 写入后 `_notify_run(run_id)` 推 SSE。
- 返回 `{"success": true, "inserted": <n>}`。
- `run_id` 不存在 → 404；`event_type` 非 `{progress, result}` → 400。

### 7.2 store 方法

```python
def record_polling_events(self, *, run_id: int, events: list[dict]) -> dict:
    # 校验 run 存在；取 request_id
    # 对每个 event: INSERT OR IGNORE INTO events(..., source_key) VALUES(...)
    # inserted > 0 时 _notify_run(run_id)
    # return {"success": True, "inserted": inserted}
```

## 8. poller 改动（`scripts/hermes_poller_cdp.py` + `hermes_translate.py`）

### 8.1 `hermes_translate.py`

- 砍掉 `callback_token` regex / `has_callback_token`（不兼容旧）。
- 新增 `events_for_store(record, db_path) -> list[dict]`：产出 `{run_id, source_key, event_type, title, markdown, payload, create_time}` 列表，规则见 §5。只对**绑定到 relay run** 的 turn 产出；unbound turn 跳过。
- `translate_record`（debug `.events.json`）保留，同步去 `callback_token`。

### 8.2 `hermes_poller_cdp.py`

- translate 后调 `events_for_store`，按 `run_id` 分组，POST 到 `POST /internal/runs/{run_id}/polling-events`。
- 从仓根 `.env` 读 `WORKSPACE_AGENT_RELAY_AUTH_TOKEN` + relay base url（默认 `http://127.0.0.1:8799`）。
- 新增 `--no-apply`：只写 debug `.events.json`，不 POST。
- 新增 `--relay-url` 覆盖。

## 9. UI

**零改动**。`ThreadView` 已按 `event_type` + `payload.trace` 渲染：
- polling `progress`（非 trace）→ `NarrationItem` 渲染 agent 消息。
- polling `progress`（trace）→ `ToolTraceListItem` 渲染 `✓ tool` 行，与 callback trace 同一渲染路径。
- polling `result`（合成）→ `ResultEvent` 渲染终态。
- `payload.polling` 不被前端读取，纯实现标记。

`api/types.ts` 无字段变更（`RunEvent` 已覆盖 `event_type/title/markdown/payload`）。

## 10. 测试

### store（`tests/test_relay_store.py`）
- `record_polling_events` 幂等：同 `source_key` 二次写入 `inserted=0`，事件不重复。
- `list_events_merged` 终态去重：有 callback `result` 时 polling `result` 被丢；无 callback `result` 时 polling `result` 保留。
- `list_events_merged` 按 `created_at` 排序，polling 事件按时序插入 callback 之间。
- `list_events`（callback-only）不含 polling 事件。

### 翻译（`tests/test_hermes_translate.py`）
- `parse_relay_header`：新 header（无 `callback_token`）只取 `request_id` + `conversation_key`。
- `events_for_store`：单 turn completed → 最后一条 agent 消息成 `result`，中间消息成 `progress`；echo/user 跳过；unbound turn 不产出；多 turn 仅全局最后一条成 `result`。

### internal 路由（`tests/test_web_api.py` 或新文件）
- 无 bearer / 错 bearer → 401。
- `run_id` 不存在 → 404。
- 正确 bearer + 合法 body → 200，事件落库，`inserted` 计数正确。

## 11. 验证（AGENTS.md §4）

```bash
.venv/bin/python -m pytest tests/ -q   # 须全绿
cd frontend && pnpm run build          # 须零错误
```

端到端：
1. 启动 relay :8799 + `./scripts/dev-dashboard.sh`。
2. 启动 poller watch：`scripts/hermes_poller_cdp.py --interval 20 --agent <agt>`。
3. dashboard 发一条任务 → 看 callback 事件实时进。
4. poller 抓到对话 → POST polling-events → dashboard 同一 run 出现 agent 可见消息（含 callback 拿不到的求助/解释）+ 本地 trace，无来源标签，按时间混排。
5. 对比 callback-only run（polling 0 新增）与 callback-broken run（polling 补出 result + 求助）。

## 12. 风险

- **poller 与 server 时钟差**：polling `created_at` 取 ChatGPT 消息时间，callback 取 server 时间；两者都是 ~real time，排序可靠，极端差几秒可接受。
- **部分唯一索引兼容性**：SQLite 3.8+ 支持部分索引，Python 自带 sqlite3 远高于此，无风险。
- **poller 跨进程读 `lookup_run`**：只读连接，不与 server 写冲突（SQLite 允许并发读）。

## 变更记录

- **2026-06-28**：初稿。锁定 polling 映射到现有 event_type、`source_key` 部分唯一索引幂等、internal 端点单写者、读取端仅终态去重、UI 零改。
- **2026-06-29**：§7.3 锁定结构排序 `(turn_ord, lane, sub)`；`steer_run` / `record_tool_trace` 写入 `turn_ord`，与 `hermes_translate` 的 turn 计数对齐。禁止用 event id 段推断作为长期方案（仅 legacy 读路径回退）。

## 7. 结构合并 v2（排序与槽位，无 hard code）

### 7.1 问题

- ChatGPT assistant 消息的 `create_time` 是流式完成时间，常晚于 callback `ask_user` / `user_message`，按时间排序会把 polling 推到 question 或答案后面。
- 用 `q_md in poll_md` 去重是正文启发式，违反「不把具体场景写进代码」。

### 7.2 写入（`events_for_store`）

对每个绑定 run 的 mapping 消息维护：

| 字段 | 含义 |
|------|------|
| `turn_ord` | 该 run 下第几个 user 节点（从 0 起，每遇到一个带 `request_id` 的 user 节点 +1） |
| `mapping_ord` | 消息在 flatten 列表中的序号（稳定、与 create_time 无关） |
| `create_time`（写入 store） | **当前 turn 的 user 节点 `create_time`**（turn 锚点），非 assistant 完成时间 |

payload 携带 `turn_ord`、`mapping_ord`（实现标记，前端不读）。

### 7.3 读取（`list_events_merged`）

排序键（**结构合并**，不混用 server 时间与 turn 锚点）：

| 事件 | `turn_ord` | lane | sub |
|------|------------|------|-----|
| dashboard `user_message`（steer） | 写入时：已有 steer 数 + 1 | 0 | `id` |
| callback tool trace | 写入时：当前 active turn（最近 steer，无 steer 则为 0） | 1 | `id` |
| 其他 callback | payload `turn_ord` 或 legacy 推断 | 1 | `id` |
| polling | payload `turn_ord` + `mapping_ord` | 2 | `mapping_ord` |

合并后按 `(turn_ord, lane, sub, id)` 排序。同一 turn 内：**用户 steer → 本地 tool traces → Hermes 可见消息**。

纯 relay（无 polling 平面）仍用 `(created_at, …)` 时间排序。

去重（仅结构）：

- callback `result` 优先于 polling `result`（已有）
- **禁止**正文子串匹配
- 待办：`ask_user` 在 question payload 写入 `turn_ord` 后，同 `turn_ord` 的 polling `progress`（非 trace）若 callback 已有 `question` 则丢弃（槽位归属，非场景分支）

## 8. 交互感知轮询（poller 策略）

- **从未打开**：relay `conversations.first_viewed_at IS NULL` 且关联 run 均已终态 → poller **不** `fetch_conversation`。
- **已打开或仍有热 run**：`GET /internal/polling-targets?trigger_id=<agt_>` 返回 `fetch_hermes_ids`；poller 默认仅拉这些 Hermes 会话（`--no-smart` 恢复全量）。
- **当前正在看**：dashboard `POST /api/conversations/{id}/presence` 心跳 → `presence_at` 新鲜 → `fast_hermes_ids`，watch 间隔 5s；否则 60s。
- **绑定**：`POST /internal/runs/{id}/polling-events` 可带 `hermes_conversation_id`，写入 `runs.hermes_conversation_id` 供下轮 targets 查询。
- **发现**：仍有热 run 但未绑定 Hermes id 时 `discover_in_progress=true`，每轮最多 `--discovery-limit` 个 in-progress Hermes 列表项用于 request_id 关联。

## 9. Pull interaction mode（conversation 级）

- `conversations.interaction_mode`：`relay`（默认）| `pull`；dashboard header 切换，`PATCH /api/conversations/{id}`。
- Pull trigger 头：`request_id` + `conversation_key` + `relay_mode: pull`（**无** `relay_mcp:`、**无** completion contract）。
- `build_trigger_input(interaction_mode="pull")` 为唯一文案源；[`runs.py`](src/workspace_agent_relay_mcp/api/routes/runs.py) create/steer 读 conversation 模式。
- `runs.interaction_mode` 在 create 时快照。
- Agent：**禁止** relay MCP 回调；**仍** `bind_relay_run`（tool trace）；可见消息靠 Hermes polling 进合并时间线。
- 与 relay callback **互斥**于同一 turn；读取端无需改 merge 逻辑。
