# AGENTS.md — workspace-agent-relay-mcp

约定给在本仓干活的 AI agent（以及未来接手的人）看。先读这份，再动手。

## 1. 这是什么仓

一个**本地优先、单用户**的 relay：给 ChatGPT Workspace Agent 提供一个回调 MCP + 实时 dashboard，补上 trigger API「发了就丢、拿不回结果」的缺口。

- 不是产品，是学习 / 原型仓。
- 依赖一个**独立的兄弟仓** `notion-local-ops-mcp`（agent 的干活工具），两者通过 `POST /internal/tool-trace` 协作。本仓是接收端。
- 根目录上一级 `~/poke/AGENTS.md` 的总则也适用（学习仓、证据优先、不擅自改上游、中文输出）。

## 2. 改动边界

### 默认允许
- 改 `src/`、`frontend/src/`、`tests/`、`scripts/`、`docs/`。
- 加测试、加文档、加 spec。

### 谨慎对待
- `store/relay_store.py` 是数据层核心，改动要配测试（callback_token 哈希、redaction、plan/event 形状都有断言）。
- `trigger.py` 里拼 `input_text` 的措辞和 `MCP_INSTRUCTIONS`（在 `server.py`）要和 `docs/agent-instructions.md` 三处口径保持一致——改一处要同步另两处。
- 前端 `api/types.ts` 的类型要和后端 `_run_detail` / event payload 对齐。

### 不要做
- 不要提交 `.env`、`cloudflared.local.yml`、`*.sqlite*`（已在 `.gitignore`，但别手动 add）。
- 不要把真实的 `AUTH_TOKEN`、`AGENT_TOKEN`、`callback_token`、私钥写进任何被跟踪的文件。
- 不要在没有 spec 的情况下大改协议形状（plan / progress / trace payload）。先写 `docs/superpowers/specs/YYYY-MM-DD-*.md`。

## 3. 怎么跑

```bash
# 后端（API + MCP + SSE），从仓根跑：
.venv/bin/python -m workspace_agent_rel-mcp.server     # 或装好后直接 workspace-agent-relay-mcp
# 默认 127.0.0.1:8799；读当前目录或仓根的 .env

# 带 cloudflared tunnel + supervisor（rolling-reload）：
./scripts/dev-tunnel.sh           # start | reload | status

# 前端 dashboard（开发）：
cd frontend && npm run dev

# 前端构建（会输出到 frontend/dist，被后端托管）：
cd frontend && npm run build      # = tsc -b && vite build；这是前端无单测时的正确性门槛
```

本机两个服务通常由 launchd 管：
- `com.workspace-agent-relay.dev-tunnel`
- `com.notion-local-ops.mcp`（兄弟仓）

重启拿新代码用 `launchctl kickstart -k gui/$(id -u)/<label>`。不要直接 `kill -9` 子进程——supervisor 会把它当异常退出处理。

## 4. 怎么验

```bash
.venv/bin/python -m pytest tests/ -q          # 后端；应全绿
cd frontend && npm run build                  # 前端；TS + 构建零错
```

- 后端测试覆盖了 store、API 路由、MCP 工具、redaction、tool-trace 端点。
- 前端**没有单元测试**，`npm run build` 是唯一门槛。改前端后必须 build 通过。
- 端到端（agent 真的 bind + 调工具 + trace 流到 dashboard）只能靠发一个真实 Workspace Agent run 来验——`callback_token` 是哈希存的，伪造不了。

## 5. 协议形状（别凭记忆，读代码确认）

- **plan**：`record_plan` 写 `plans` 表（`steps_json`）。每个 step 有稳定 `id` + `title` + `status`。`record_progress` 的 `step_updates` 用同一个 `id` 更新状态。
- **progress event**：`event_type="progress"`，payload 里 `trace: true` 表示是 notion-local-ops 自动镜像的工具调用；否则是 agent 主动写的 narration。前端 `ThreadView` 按这个标志分流渲染。
- **trace payload**：`{trace, tool, title, args_summary, result_summary, started_at, duration_ms, ok, error}`。`/internal/tool-trace` 用 body 里的 `callback_token` 鉴权（不是 dashboard bearer），closed run 返回 409。

## 6. 文档沉淀

- 设计 / 决策：`docs/superpowers/specs/YYYY-MM-DD-<topic>.md`。
- 给 agent 用的 instructions：`docs/agent-instructions.md`（正文在反引号块里，可直接复制到 ChatGPT）。
- 同一天同主题追加，不重复开新文件。

## 7. 输出偏好

- 简体中文。
- 给结论、关键证据、验证状态、下一步最小动作。
- 改了协议 / 指令，明确说「同步了哪几处」。
