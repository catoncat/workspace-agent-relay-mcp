# Relay ↔ notion-local-ops 桥接设计（方案 C）

日期：2026-06-26
状态：待用户 review

## 背景与动机

至此已有两件事：

1. **relay MCP**（`workspace-agent-relay-mcp`）是 ChatGPT Workspace Agent 的本地回调面，已实现 `record_plan` / `record_progress(step_updates)` / `record_result` / `ask_user`。它靠 Agent **主动转述**自己在做什么。
2. **notion-local-ops MCP**（`notion-local-ops-mcp`，同栈 FastMCP）是 Agent **干活用的工具集**：文件读写、搜索、shell、git、delegate_task。Agent 调 `apply_patch` / `git_commit` / `run_command` 时，这些调用全部经过 notion-local-ops 的 Python 进程。

此前结论「Workspace Agent 内部工具调用从外部不可观测」只对** ChatGPT 自带的内部工具**成立。一旦 Agent 用的干活工具在我们自己的 MCP 里，**我们就是工具执行者，每次调用天然经过我们**。不利用这一点，等于让 Agent 边干活边手动转述，既污染它的上下文，又丢失了真实的工具调用细节。

本设计把两个 MCP 粘起来，让 notion-local-ops 在执行干活工具时**自动**把工具调用 trace 回传给 relay，Agent 上下文零污染，relay UI 复现接近 ChatGPT 的工具树。

## 核心原则

- **notion-local-ops 保持通用**：桥接是 opt-in，不 bind 时行为与今天完全一致，Notion agent 等其他使用者不受影响。
- **Agent 上下文成本最低**：只多调一次 `bind_relay_run`，之后干活工具 silent 上报，Agent 不参与。
- **relay 仍是操作者可视面的唯一 source**：notion-local-ops 不直接渲染，只回传；前端只读 relay。
- **不合并进程/仓库**：两个 MCP 各自独立运行，各自独立 venv/launchd/connector。协作靠 HTTP。

## 通用 instrumentation 抽象（为什么对 notion-local-ops 不算污染）

notion-local-ops 这边的改动刻意分两层，使「可观测」成为通用能力而非 relay 专用触角：

1. **通用 instrumentation 层**（`instrument.py`，零 relay 痕迹）：`@traced` 装饰器、`ToolSink` 协议、`register_sink`/`notify_sinks`。任何工具套上 `@traced` 就会记时、提取参数摘要、捕获结果/异常、通知所有已注册 sink。无 sink 注册时开销忽略不计。
2. **relay sink**（`relay_bridge.py`，实现 `ToolSink`）：由 `bind_relay_run` 在运行时注册激活；不 bind 则该 sink 不存在，行为与今天一致。

这对应 observer pattern（OpenAI Agents SDK 的 `TracingProcessor`、Python `logging`、Datadog APM 同构）。relay 只是第一个消费者；日后可挂日志/指标/其他观察者 sink 而无需再改工具层。

检验标准：若 relay 项目废了，通用 instrumentation 层仍是 notion-local-ops 的有用基础设施，不是该回退的垃圾。因此对 notion-local-ops 是能力增强，不是污染。Notion agent 等不调 bind 的使用者体验完全不变。

## 架构

```
ChatGPT Workspace Agent
   │
   ├── relay MCP ── record_plan / record_progress / record_result / ask_user
   │      │
   │      └── SQLite (runs/events/plans) ── SSE ──▶ relay 前端
   │      ▲
   │      │ HTTP POST /internal/tool-trace  (本设计新增)
   │      │
   └── notion-local-ops MCP
          │
          ├── bind_relay_run(request_id, callback_token, relay_url)  ← Agent 调一次
          ├── apply_patch / write_file / git_* / run_command / read_text / search / ...
          │      │
          │      └── 每次工具执行后，hook 读取进程级绑定，POST trace 到 relay
          │
          └── (不 bind 时：无任何回传，行为不变)
```

## 协议

### notion-local-ops 侧：`bind_relay_run` 工具

```json
{
  "request_id": "run_...",
  "callback_token": "secret",
  "relay_url": "http://127.0.0.1:8799",
  "conversation_key": "optional, 用于校验"
}
```

行为：

- 在 `session.py` 新增进程级 `_bound_run`（与现有 `_default_cwd` 同模式）：`{request_id, callback_token, relay_url, conversation_key, bound_at}`。
- 绑定是**进程级单值**（与 notion-local-ops 的单 session 模型一致）。新 bind 覆盖旧 bind；传 `null` 清除绑定。
- 不校验 relay 可达性（bind 是本地的，relay 挂了不挡干活）；回传失败时静默丢弃（见下）。
- 返回 `{success, bound: true, request_id}`。

### notion-local-ops 侧：工具执行 hook

在 server.py 的每个 `@mcp.tool` handler 外包一层 wrapper（或在 handler 末尾统一调用），**所有工具**执行后触发上报。上报内容分两类：

**调用元数据**（始终上报，体积小）：

```json
{
  "tool": "apply_patch",
  "title": "apply_patch → ThreadView.tsx",
  "args_summary": {"path": "frontend/src/components/ThreadView.tsx", "hunks": 3},
  "started_at": "...",
  "duration_ms": 42,
  "ok": true,
  "error": null
}
```

**结果**（截断/指针，不全量）：

- 读类（read_text/list_files/search/git_status/git_diff/git_log/git_show/git_blame）：只回传 `result_summary`（如 `{lines: 200, bytes: 12000, truncated: true}`），不回传内容本体。
- 写类（apply_patch/write_file/git_commit/run_command）：回传 `result_summary` + 关键结果字段（如 git_commit 的 `{commit: "abc123", files: 3}`，run_command 的 `{exit_code: 0, stdout_tail: "..."}`，stdout_tail 截断到 ~500 字符）。
- delegate_task / run_command_stream：上报启动事件，后续 get_task/wait_task 查询时再上报状态变化。

`args_summary` 由每个工具的 wrapper 自定义提取（不直接 dump 全部参数，避免大参数爆炸，如 write_file 的 `content` 只报 `{bytes: N}`）。

### relay 侧：`POST /internal/tool-trace`

新增内部端点（不走 `/api`，单独挂 `/internal`，仍需 bearer auth 但用**回调 token 校验**而非 dashboard token，因为 notion-local-ops 拿到的是 callback_token）：

```json
POST /internal/tool-trace
Authorization: Bearer <callback_token>
{
  "request_id": "run_...",
  "conversation_key": "...",
  "tool": "apply_patch",
  "title": "apply_patch → ThreadView.tsx",
  "args_summary": {...},
  "result_summary": {...},
  "started_at": "...",
  "duration_ms": 42,
  "ok": true,
  "error": null
}
```

行为：

- 用 `callback_token` + `request_id` 校验（复用 `_validate_callback_conn` 逻辑）。
- 追加一条 `progress` 事件，`event_type` 仍是 `progress`（前端不改查询逻辑），`title` = trace 的 title，`markdown` = 紧凑人类可读摘要（如 `✓ apply_patch ThreadView.tsx (42ms, 3 hunks)`），`payload` = 完整 trace 结构。
- payload 里加 `trace: true` 标记，前端据此区分「Agent 主动 progress」和「工具自动 trace」。
- 不触发 plan step 翻转（trace 不是 plan 步骤；step 翻转仍由 Agent 主动 `record_progress(step_updates)` 负责）。
- run 状态不动（trace 不应把 done 状态顶回 waiting；只在 run 仍 active 时接受 trace，terminal run 的 trace 丢弃）。

### 失败语义

- notion-local-ops 上报失败（relay 不可达、超时、校验失败）→ **静默丢弃**，不影响工具执行结果。工具该返回什么返回什么。
- 上报是 fire-and-forget：短超时（如 1.5s），超时即放弃。可加一个进程级计数器 `dropped_traces` 供 server_info 暴露，便于排查。
- 不做重试队列（YAGNI；trace 丢一两条不影响操作者理解大局）。

## 前端

### 数据流

无需改查询——trace 进的是 `progress` 事件，既有 SSE 已覆盖。前端只在渲染时读 `payload.trace` 区分。

### ThreadView 渲染

- **工具 trace** 与 **Agent 主动 progress narration** 视觉区分：
  - trace：紧凑单行（图标 + tool 名 + 目标 + 耗时 + ok/err），可折叠查看 args_summary/result_summary。
  - narration：现有「Work log」折叠区。
- trace 按时间排列在 plan checklist 之下、narration 之上，形成「计划 → 工具调用流 → 文字说明 → 结果」的阅读顺序。
- 批量 trace 涌入时复用既有 stagger 动画思路，避免刷屏跳动。
- 失败 trace（`ok: false`）用红/橙色突出，便于操作者一眼看到 Agent 在哪一步炸了。

### 不做

- 嵌套工具树（parent_id）：YAGNI，先扁平时间线。delegate_task 的子任务用单独 trace 表示。
- trace 的实时 token 流：YAGNI，按调用粒度即可。

## 实现落点

### relay（`workspace-agent-relay-mcp`）

- `api/routes/`：新增 `internal.py`，挂 `/internal/tool-trace`，bearer 用 callback_token 校验路径。
- `store/relay_store.py`：新增 `record_tool_trace(...)`，内部调 `_append_event_conn` 写 progress 事件 + payload 标记 `trace: true`。校验 run 仍 active。
- `app.py`：注册 internal 路由。

### notion-local-ops（`notion-local-ops-mcp`）

- `instrument.py`（新，通用层）：
  - `ToolSink` 协议：`on_tool_event(event: ToolEvent) -> None`（同步，实现者自行决定是否阻塞；relay sink 内部 fire-and-forget）。
  - `ToolEvent` dataclass：`tool, title, args_summary, result_summary, started_at, duration_ms, ok, error`。
  - `register_sink(sink)` / `clear_sinks()` / `notify_sinks(event)`。
  - `@traced(tool_name, title_fn=None, args_fn=None, result_fn=None)` 装饰器：包住 handler，记时，调用 args_fn/result_fn 提取摘要（缺省用保守截断），调用 `notify_sinks`。装饰器对 handler 签名/返回值透明。
  - 各工具专属摘要函数（如 `_patch_args_summary`、`_read_result_summary`）放这里或工具模块旁，保持工具实现层零侵入。
- `relay_bridge.py`（新，relay 专用 sink）：实现 `ToolSink`，`on_tool_event` 内部读 session 绑定，fire-and-forget HTTP POST（短超时，静默失败）。无绑定则 no-op。
- `session.py`：新增 `_bound_run` 进程级状态 + get/set/clear（照搬 `_default_cwd` 模式）。
- `server.py`：新增 `bind_relay_run` 工具；给每个干活工具 handler 套 `@traced(...)`（一行装饰器，不动 handler 内部）。read 类工具也套，args/result 摘要按读类策略只报元数据+行数字节。
- `config.py`：新增 `RELAY_BRIDGE_TIMEOUT`（默认 1.5s）、`RELAY_BRIDGE_ENABLED`（默认 true，可全局关）。

### trigger prompt / agent instructions

- `trigger.py` 的 Completion contract 加一行：`After record_plan, call notion-local-ops.bind_relay_run with the request_id, callback_token, and this relay's URL (http://127.0.0.1:8799) so your tool calls are mirrored to the operator automatically.`
- `docs/agent-instructions.md` 加 bind 步骤。

## 测试

### relay

- `record_tool_trace` 校验 callback_token；terminal run 拒绝；active run 写 progress 事件且 payload `trace: true`。
- `/internal/tool-trace` 端点：正确 token 200、错误 token 401、未知 request_id 404。
- 既有 progress 测试不破坏。

### notion-local-ops

- **instrument 层（通用）**：`@traced` 装饰器记时正确；注册 sink 后收到 `ToolEvent`；无 sink 时不报错；args_fn/result_fn 缺省截断生效；handler 返回值/异常不被吞（异常照常抛出，trace 记 `ok:false`）。
- **relay sink**：`bind_relay_run` 设置/覆盖/清除进程级绑定；绑定后工具执行触发 `on_tool_event` 内的 HTTP POST，payload 形状正确；未绑定时不发起任何 HTTP（assert no call）；回传失败（模拟超时/5xx）不影响工具返回值。
- 既有工具测试不破坏（装饰器透明）。

### 联调（手动）

两个 server 都起，发一个测试任务，Agent bind 后干活，relay UI 应实时出现工具 trace 流。

## 未决 / 下一轮

- relay_url 怎么告诉 Agent：trigger prompt 里写死 `http://127.0.0.1:8799`，还是从 config.public_base_url 动态填？倾向后者（tunnel 场景下 Agent 看到的可能是公网 URL，但 notion-local-ops 在本机，直连 127.0.0.1 即可——所以写死本地地址更稳）。spec 里倾向**写死本地地址**，待 review 确认。
- 是否给 notion-local-ops 一个「relay 不可达时降级写本地文件」的兜底：YAGNI，先静默丢弃。
- trace 是否要带 parent 关系支持 delegate_task 嵌套：YAGNI。
