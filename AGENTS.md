# AGENTS.md — workspace-agent-relay-mcp

工作规范，适用于在本仓内执行任务的 AI agent 及协作者。执行任何变更前先阅读本文件。

## 1. 仓库定位

本地优先、单用户的 relay：为 ChatGPT Workspace Agent 提供回调 MCP 与实时 dashboard，弥补 trigger API「请求即结束、无法取回结果」的缺口。

- 定位为学习 / 原型项目，非产品。
- 与兄弟仓 [`notion-local-ops-mcp`](https://github.com/catoncat/notion-local-ops-mcp) 协作：该仓提供 agent 的执行工具，本仓接收其工具调用 trace。本仓为接收端。
- 上级目录 `~/poke/AGENTS.md` 的总则同样适用：学习仓、证据优先、不擅自修改上游、默认中文输出。

## 2. 变更边界

### 允许
- 修改 `src/`、`frontend/src/`、`tests/`、`scripts/`、`docs/`。
- 新增测试、文档、spec。

### 需谨慎
- `store/relay_store.py` 为数据层核心，任何改动须配套测试（callback_token 哈希、redaction、plan/event 结构均有断言）。
- `trigger.py` 中 `input_text` 的措辞、`server.py` 中的 `MCP_INSTRUCTIONS`、`docs/agent-instructions.md` 三处口径必须一致；修改任一处须同步另外两处。
- 前端 `api/types.ts` 的类型须与后端 `_run_detail` 及 event payload 对齐。

### 禁止
- 提交 `.env`、`cloudflared.local.yml`、`*.sqlite*`（已纳入 `.gitignore`，勿手动 `git add`）。
- 将真实 `AUTH_TOKEN`、`AGENT_TOKEN`、`callback_token` 或私钥写入任何受版本控制的文件。
- 在无 spec 的情况下大幅修改协议结构（plan / progress / trace payload）。变更前先编写 `docs/superpowers/specs/YYYY-MM-DD-*.md`。

## 3. 运行

```bash
# 后端（API + MCP + SSE），仓根执行：
.venv/bin/python -m workspace_agent_relay_mcp.server   # 或安装后直接 workspace-agent-relay-mcp
# 默认监听 127.0.0.1:8799，读取当前目录或仓根的 .env

# 带 cloudflared tunnel + supervisor（支持 rolling-reload）：
./scripts/dev-tunnel.sh        # 子命令：start | reload | status

# 前端 dashboard 开发模式：
cd frontend && npm run dev

# 前端构建（输出至 frontend/dist，由后端托管）：
cd frontend && npm run build   # 等价于 tsc -b && vite build
```

本机两个服务通常由 launchd 托管：
- `com.workspace-agent-relay.dev-tunnel`
- `com.notion-local-ops.mcp`（兄弟仓）

重启以加载新代码时使用 `launchctl kickstart -k gui/$(id -u)/<label>`。避免直接 `kill -9` 子进程，supervisor 会将其视为异常退出。

## 4. 验证

```bash
.venv/bin/python -m pytest tests/ -q     # 后端，须全绿
cd frontend && npm run build             # 前端，TS 与构建均须零错误
```

- 后端测试覆盖 store、API 路由、MCP 工具、redaction、tool-trace 端点。
- 前端无单元测试，`npm run build` 为唯一正确性门槛；修改前端后必须通过 build。
- 端到端验证（agent 实际 bind + 调用工具 + trace 流达 dashboard）须通过发起真实 Workspace Agent run 完成，因 `callback_token` 仅以哈希存储，无法伪造。

## 5. 协议结构

以下为概要，具体以代码为准。

- **plan**：`record_plan` 写入 `plans` 表（`steps_json`）。每个 step 包含稳定 `id`、`title`、`status`。`record_progress` 的 `step_updates` 通过相同 `id` 更新状态。
- **progress event**：`event_type="progress"`；payload 中 `trace: true` 表示由 notion-local-ops 自动镜像的工具调用，否则为 agent 主动写入的 narration。前端 `ThreadView` 依此标志分流渲染。
- **trace payload**：`{trace, tool, title, args_summary, result_summary, started_at, duration_ms, ok, error}`。`/internal/tool-trace` 使用 body 中的 `callback_token` 鉴权（非 dashboard bearer），对已关闭的 run 返回 409。
- **agent token_ref**：agent 记录只存 `env:<VAR_NAME>` 形式的引用，不存 token 值。`VAR_NAME` 必须为 `WORKSPACE_AGENT_RELAY_AGENT_TOKEN` 或以 `WORKSPACE_AGENT_RELAY_AGENT_TOKEN_` 开头（白名单，见 `api/validation.py`），越权值（如 `env:HOME`）一律拒绝。`agent_token(config, token_ref)` 在 trigger 时按 ref 解析 token；token 值仅在启动时从环境快照进 `RelayConfig.agent_tokens`，不入库、不回前端。`GET /api/agents/token-refs` 只返回已配置的 ref（env var 名），不含 token 值，供前端「创建 agent」表单下拉。新增/轮换 token 须改 `.env` 并重启 relay。

## 6. 文档沉淀

- 设计与决策：`docs/superpowers/specs/YYYY-MM-DD-<topic>.md`。
- Agent 指令：`docs/agent-instructions.md`（正文位于代码块内，可直接复制至 ChatGPT）。
- 同日同主题追加更新，不重复创建文件。

## 7. 输出偏好

- 默认简体中文。
- 给出结论、关键证据、验证状态、下一步最小动作。
- 涉及协议或指令变更时，明确说明同步了哪些位置。
