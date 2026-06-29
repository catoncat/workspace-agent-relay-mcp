# AGENTS.md — workspace-agent-relay-mcp

工作规范，适用于在本仓内执行任务的 AI agent 及协作者。执行任何变更前先阅读本文件。

## 1. 仓库定位

本地优先、单用户的 relay：为 ChatGPT Workspace Agent 提供回调 MCP 与实时 dashboard，弥补 trigger API「请求即结束、无法取回结果」的缺口。

- 定位为学习 / 原型项目，非产品。
- 与兄弟仓 [`notion-local-ops-mcp`](https://github.com/catoncat/notion-local-ops-mcp) 协作：该仓提供 agent 的执行工具，本仓接收其工具调用 trace。本仓为接收端。
- **双平面**：callback 补**本地执行面**（notion-local-ops trace、结构化 plan/result）；Hermes polling 补**云端可见面**（agent 叙述、ChatGPT 原生工具）。dashboard 看合并时间线，polling 不能替代 relay。
- 上级目录 `~/poke/AGENTS.md` 的总则同样适用：学习仓、证据优先、不擅自修改上游、默认中文输出。

## 2. 变更边界

### 允许
- 修改 `src/`、`frontend/src/`、`tests/`、`scripts/`、`docs/`。
- 新增测试、文档、spec。

### 需谨慎
- `store/relay_store.py` 为数据层核心，任何改动须配套测试（plan/event 结构、run 状态收盘、`source_key` polling 幂等、`list_events_merged` 终态去重、`interaction_mode` / `hermes_conversation_id` / `conversations.presence_at` 等列迁移均有断言）。
- **relay 模式**三处口径必须一致：`trigger.py` 中 `input_text` 的措辞、`server.py` 中的 `MCP_INSTRUCTIONS`、`docs/agent-instructions.md`。修改任一处须同步另外两处。
- **pull 模式**另有一套 trigger 文案（`build_trigger_input(interaction_mode="pull")` 产出 `relay_mode: pull`，无 MCP completion contract）；须同步 `trigger.py` pull 分支、`server.py` MCP_INSTRUCTIONS 中的 pull 禁令、以及 `docs/agent-instructions.md` 对应段落。
- 前端 `api/types.ts` 的类型须与后端 `_run_detail` 及 event payload 对齐。

### 禁止
- 提交 `.env`、`cloudflared.local.yml`、`*.sqlite*`（已纳入 `.gitignore`，勿手动 `git add`）。
- 将真实 `AUTH_TOKEN`、`AGENT_TOKEN` 或私钥写入任何受版本控制的文件。
- 在无 spec 的情况下大幅修改协议结构（plan / progress / trace payload、polling 映射、merge 语义）。变更前先编写 `docs/superpowers/specs/YYYY-MM-DD-*.md`。

## 3. 运行

```bash
# 后端（API + MCP + SSE），仓根执行：
.venv/bin/python -m workspace_agent_relay_mcp.server   # 或安装后直接 workspace-agent-relay-mcp
# 默认监听 127.0.0.1:8799，读取当前目录或仓根的 .env

# 带 cloudflared tunnel + supervisor（支持 rolling-reload）：
./scripts/dev-tunnel.sh        # 子命令：start | reload | status
# 健康检查通过后会尝试拉起 Hermes poller（见下）

# Hermes poller（polling 平面；dev-tunnel 自动尝试，也可手动）：
# 前提：Chrome CDP 可达（默认 HERMES_CDP=http://127.0.0.1:9223）+ agents.hermes_agent_id 已绑定
.venv/bin/python scripts/hermes_poller_cdp.py --agent agt_xxx --interval 20
# poller 不直写 SQLite，translate 后 POST /internal/runs/{id}/polling-events（单写者 = relay server）
# 调试只写 .events.json、不 POST：加 --no-apply

# 前端 dashboard 开发模式（推荐日常改 UI 时使用）：
./scripts/dev-dashboard.sh     # 检查后端健康 → Vite :5173，/api 代理到 :8799
# 从仓根 .env 自动注入 WORKSPACE_AGENT_RELAY_AUTH_TOKEN，无需在 :5173 再粘贴

# 等价手动启动：
cd frontend && pnpm dev

# 前端构建（输出至 frontend/dist，由后端 :8799 托管；仅 CI 或需要单端口 dashboard 时）：
cd frontend && pnpm run build   # 等价于 tsc -b && vite build
```

日常开发：**后端 :8799 常驻 + `./scripts/dev-dashboard.sh` 打开 :5173**。不必每次改 UI 都 build。polling 要看到云端消息还需 CDP + poller 在跑。

本机两个服务通常由 launchd 托管：
- `com.workspace-agent-relay.dev-tunnel`
- `com.notion-local-ops.mcp`（兄弟仓）

重启以加载新代码时使用 `launchctl kickstart -k gui/$(id -u)/<label>`。避免直接 `kill -9` 子进程，supervisor 会将其视为异常退出。

## 4. 验证

```bash
.venv/bin/python -m pytest tests/ -q     # 后端，须全绿
cd frontend && pnpm run build          # 前端，TS 与构建均须零错误
```

- 后端测试覆盖 store（含 `record_polling_events`、`list_events_merged`）、API 路由、MCP 工具、redaction、`/internal/tool-trace` 与 `/internal/runs/{id}/polling-events`、`tests/test_hermes_translate.py`。
- 前端无单元测试，`pnpm run build` 为唯一正确性门槛；修改前端后必须通过 build。
- 端到端（callback）：发起真实 Workspace Agent run → agent bind + 调用工具 + trace 流达 dashboard；MCP 经 OAuth/bearer 鉴权，`/internal/tool-trace` 经 shared bearer 投递，无法离线伪造。
- 端到端（polling merge）：relay :8799 + `dev-dashboard.sh` + `hermes_poller_cdp.py` → 同一 run 时间线出现 callback trace 与 polling 可见消息，按时间混排、无来源标签；callback `result` 优先于 polling 合成 `result`。详见 `docs/superpowers/specs/2026-06-28-polling-merge.md` §11。

## 5. 协议结构

以下为概要，具体以代码与 spec 为准。

### 5.1 Callback 平面（MCP + tool-trace）

- **plan**：`record_plan` 写入 `plans` 表（`steps_json`）。每个 step 包含稳定 `id`、`title`、`status`。`record_progress` 的 `step_updates` 通过相同 `id` 更新状态。
- **progress event**：`event_type="progress"`；payload 中 `trace: true` 表示由 notion-local-ops 自动镜像的工具调用，否则为 agent 主动写入的 narration。前端 `ThreadView` 依此标志分流渲染。
- **trace payload**：`{trace, tool, title, args_summary, result_summary, started_at, duration_ms, ok, error}`。`/internal/tool-trace` 使用 shared bearer（`WORKSPACE_AGENT_RELAY_AUTH_TOKEN`，非 dashboard OAuth）鉴权，对已关闭的 run 返回 409。
- **MCP 鉴权**：已移除 per-run `callback_token`；`/mcp` 靠 OAuth/bearer + `request_id` 路由 + `conversation_key` 校验。
- **agent token**：Dashboard 创建/更新 agent 时通过 `access_token` 写入 relay SQLite（`token_ref=local:<id>`），值不回前端。Legacy 仍支持 `env:<VAR_NAME>`（白名单见 `api/validation.py`）。`resolve_agent_token(config, store, token_ref)` 在 trigger 时解析；env token 仍从启动快照 `RelayConfig.agent_tokens` 读取。

### 5.2 Polling 平面（Hermes → internal POST）

- **写入**：`scripts/hermes_poller_cdp.py` + `hermes_translate.events_for_store` → `POST /internal/runs/{run_id}/polling-events`（bearer 同 tool-trace）。`events.source_key` 非 NULL 表示 polling 来源（ChatGPT mapping `node_id`），`(run_id, source_key)` 部分唯一索引保证幂等。
- **映射**：对话节点映射到现有 `event_type`（`progress` / 合成 `result`），payload 带 `polling: true` 等实现标记；前端不读来源标签。规则见 `docs/superpowers/specs/2026-06-28-polling-merge.md` §5。
- **拉取策略**：`GET /internal/polling-targets` 按 dashboard `POST /api/conversations/{id}/presence` 心跳与热 run 决定拉哪些 Hermes 会话；未打开且已终态的 conversation 不 fetch。

### 5.3 读取合并与 interaction_mode

- **合并读取**：dashboard 与 SSE 用 `list_events_merged`（callback + polling，callback `result` 优先去重，按 turn 锚点 + `mapping_ord` 排序）。`get_run_context` 仍用 callback-only 的 `list_events`（agent 不需要读 polling 镜像）。
- **interaction_mode**（conversation 级，`relay` | `pull`）：`relay` 为默认，agent 经 MCP 回调 plan/progress/result；`pull` 禁止该 turn 使用 relay MCP 工具写可见消息，仍 `bind_relay_run` 收 tool trace，可见叙述靠 polling 进合并时间线。trigger 文案由 `build_trigger_input(interaction_mode=...)` 统一产出。

## 6. 文档沉淀

- 设计与决策：`docs/superpowers/specs/YYYY-MM-DD-<topic>.md`。
- Agent 指令：`docs/agent-instructions.md`（正文位于代码块内，可直接复制至 ChatGPT）。
- 同日同主题追加更新，不重复创建文件。

## 7. 输出偏好

- 默认简体中文。
- 给出结论、关键证据、验证状态、下一步最小动作。
- 涉及协议或指令变更时，明确说明同步了哪些位置。
