# Relay Plan + Progress 协议设计

日期：2026-06-26
状态：已与用户确认，待落实施计划

## 背景与动机

当前 relay 只能展示 Agent 主动通过 MCP 写回的 `record_progress` 事件，每条是一个独立 Tool 卡片。实际观察到两个问题：

1. **展示粗糙、不实时**：Agent 只在 milestone 级别回 progress，本地操作者在两三个粗粒度卡片之间干等，没有「正在做第几步」的结构感。
2. **Agent 已在做计划，但操作者看不到**：ChatGPT Workspace Agent 内部会调它自己的 plan 工具、显示在 ChatGPT 侧的 Plan 卡片里。这个计划不经过我们的 MCP，本地操作者是「瞎」的——Agent 不知道这件事。

调查结论（决定协议边界）：

- Workspace Agent trigger API 是**单向投递**：`POST /v1/workspace_agents/{id}/trigger` → `202 Accepted`，无 body、无 run ID、无流式、无工具调用回传。官方文档明确「agent response cannot currently be retrieved through the API」。
- Agents SDK 的 `TracingProcessor` / `FunctionSpan` 只在**自己跑 SDK 进程**时可挂载；ChatGPT 侧运行时的 tracing 对外部不可观测。
- ChatGPT 界面无法被 iframe 嵌入（`X-Frame-Options` + CSP）。companion window（独立窗口）是可行的，但本轮不做，靠 Chrome 原生 split view 由用户自行并排。

由此，**不可能从外部捕捉 Agent 的内部工具调用**。唯一可行路径是：让 Agent 把「已经做的事」说给操作者听。

## 核心设计原则

把 relay 从「汇报通道」重新定义为「Agent 的外部工作记忆 + 操作者可视面」。关键约束：记录工具对 Agent 必须**有用、不是垃圾信息**，否则会污染/膨胀 Agent 上下文，且 Agent 会抗拒调用。

满足「对 Agent 有用」的三个机制：

1. **盲区沟通**：trigger prompt 明确告知「本地操作者看不到你 ChatGPT 侧的计划与工具调用，relay 是操作者跟踪你的唯一通道」。Agent 一旦理解 *why*，记录就变成正当沟通而非汇报义务。
2. **批量打包**：`record_progress` 接受 `step_updates[]`，一次翻转多个步骤状态。Agent 完成若干步后批量同步，调用次数低、上下文污染可控，同时前端一次吃多条信息有运动感。
3. **返回即收益**：每次记录工具返回一个紧凑状态快照（当前 plan、各步状态、已用时、最近事件摘要）。Agent 调用它不是「花钱汇报」，而是「花钱买一次 orientation」，尤其对长任务/可能丢上下文的 Agent 真有用。完整重定向走 `get_run_context`，记录工具做轻量快照。

## 协议

### 数据模型：plan

每个 run 至多一个 plan，由若干 step 组成。step 用 Agent 提供的稳定 `id` 标识（用于后续状态翻转）。

```json
{
  "created_at": "...",
  "updated_at": "...",
  "steps": [
    {"id": "s1", "title": "确认改动边界", "status": "done", "note": "..."},
    {"id": "s2", "title": "修复 Header", "status": "in_progress", "note": "..."},
    {"id": "s3", "title": "运行前端验证", "status": "pending"}
  ]
}
```

step `status` 取值：`pending` | `in_progress` | `done` | `skipped`。

### 新工具 `record_plan`

参数：

```json
{
  "request_id": "run_...",
  "callback_token": "secret",
  "conversation_key": "...",
  "steps": [
    {"id": "s1", "title": "确认改动边界"},
    {"id": "s2", "title": "修复 Header"}
  ]
}
```

行为：

- 校验 callback。
- 若该 run 已有 plan：以新 steps **替换**（允许 Agent 修订计划）。
- 否则创建 plan。
- run 状态保持不变（不强制进 waiting）。
- 返回当前 plan 快照。

约束：`steps` 数量 1–20，`id` 在同一 plan 内唯一，`title` 非空且 ≤ 200 字符。超限返回 400 风格错误（success:false + error）。

### 扩展 `record_progress`

新增可选参数 `step_updates`，与既有 `message`/`title` **并存**（向后兼容，旧调用仍有效）：

```json
{
  "request_id": "run_...",
  "callback_token": "secret",
  "conversation_key": "...",
  "message": "可选的一句工具摘要 narration",
  "title": "可选标题",
  "step_updates": [
    {"id": "s2", "status": "done", "note": "Header 已统一图标尺寸"},
    {"id": "s3", "status": "in_progress"}
  ]
}
```

行为：

- 校验 callback。
- 追加一条 `progress` 事件（含 message/title）。
- 若提供 `step_updates`：按 `id` 翻转对应 step 的 status/note。未在 plan 中的 `id` 忽略（不报错，记录在事件 payload 的 `ignored_step_ids`）。
- run 状态 → `waiting`（沿用既有语义）。
- 返回当前 plan 快照 + event_id。

一次调用可只传 `step_updates` 不传 `message`（纯状态翻转），或只传 `message`（旧式纯文本进度），或两者都传。

### 工具返回值（统一）

`record_plan` 和 `record_progress` 返回：

```json
{
  "success": true,
  "event_id": 123,
  "plan": {
    "steps": [{"id": "s1", "title": "...", "status": "done", "note": "..."}]
  },
  "run_status": "waiting"
}
```

`plan` 可为 `null`（无 plan 时）。这是「调用即收益」的轻量快照。

### Trigger prompt 措辞

`build_trigger_input` 的 Completion contract 段改为强调盲区 + 计划优先 + 批量同步：

```
Completion contract:
本地操作者看不到你在 ChatGPT 侧的计划与工具调用，relay 是操作者跟踪你的唯一通道。
开始前，调用 workspace-agent-relay-mcp.record_plan 给出你的步骤计划。
完成若干步后，调用 workspace-agent-relay-mcp.record_progress 批量同步步骤状态（step_updates），并可选附一句工具摘要。
被用户决策卡住时调用 workspace-agent-relay-mcp.ask_user。
完成前调用 workspace-agent-relay-mcp.record_result 给出 status、title 与完整 Markdown 结果。
不要只在 ChatGPT 对话里回答。
```

### MCP_INSTRUCTIONS 同步更新

server.py 的 `MCP_INSTRUCTIONS` 改为强调「operator 唯一窗口」+ 完整 workflow，并说明每次调用返回 plan 快照（让 Agent 知道调用有收益）。

### 工具描述按 OpenAI MCP 最佳实践打磨

依据 OpenAI 官方对 MCP 工具的建议（描述用「Use this when…」开头、给出 when to use 与 what it returns、含 1-5 个例子、参数加 enum/约束、输出只返回下一步所需数据），所有五个工具的 `description` 重写为动词引导句 + 调用时机 + 返回值 + 一个 JSON 例子；参数改用 `Annotated[..., Field(description=..., json_schema={enum/min/max})]` 暴露枚举与约束（`status` 枚举、`steps` 1-20、`limit` 1-20）。目的是让 Agent 在工具选择阶段就更可能挑对工具、按预期调用，减少 prompt 层的额外规训。

## 前端

### 数据流

- `RunDetail` 新增 `plan: Plan | null`。
- `/api/runs/{id}` 与 SSE stream 的 detail payload 携带 `plan`。
- `record_plan` / `record_progress` 的 step 状态变化通过既有 `RunEventBus` 推送，前端 SSE 自动收到新 detail。

### ThreadView 渲染

每个 run 按以下顺序渲染（时间正序，已修）：

1. **user 消息**（`run.input_markdown`）— user bubble。
2. **plan 区块**（若存在）— live checklist：
   - 每个 step 一行：状态图标 + title + 可选 note。
   - 状态图标：`done` ✓（绿）/ `in_progress` 旋转圈 / `pending` 空圈 / `skipped` 横线。
   - step 从 `pending`→`in_progress`→`done` 的翻转带短暂过渡动画（CSS transition / framer-motion 已可用则用）。
   - 批量 step_updates 到达时，多个 checkbox 依次翻转（stagger，~80ms 间隔），制造「一阵进度涌进来」的运动感。
3. **progress narration**（若该 progress 事件有 message）— 折叠在可展开的「工作过程」区块里（复用 `reasoning.tsx` 风格），默认折叠历史 narration，最新一条可展开。避免长 markdown 淹没对话。
4. **question** — 提问气泡（既有）。
5. **result** — **改为 assistant 聊天气泡**而非 bordered 卡片，更像聊天。artifacts 仍以 badge 列出。
6. 终态无 result 时 — TerminalStatus 提示（既有）。

### 无 plan 降级

若 run 无 plan 但有零散 progress 事件：把所有 progress 折成一条「工作过程」可折叠区块，不渲染 checklist。UI 同时处理「有 plan」「无 plan」两种形态。

### 不做

- 不做 companion window / iframe 入口（本轮砍掉，靠 Chrome split view）。
- 不试图复刻 ChatGPT 工具树（数据源不可得）。
- 不强制 plan（prompt 鼓励 + 降级展示，Agent 不听话也能看）。

## 后端实现落点

### store/relay_store.py

- schema 新增 `plans` 表：`run_id`、`steps_json`、`created_at`、`updated_at`，run_id 唯一。
- 新增 `record_plan(...)`：校验 callback → upsert plan（replace steps）→ 通知 run。
- 扩展 `record_progress(...)`：新增 `step_updates` 参数；在事务内按 id 更新 plan steps_json；事件 payload 记录 `step_updates` 与 `ignored_step_ids`。
- 新增 `get_plan(run_id)`：返回 plan dict 或 None。
- `_run_detail`（在 routes/runs.py）拼接 `plan`。
- `_notify_run` 的 payload 增加 `plan` 字段。

### server.py

- 注册 `record_plan` MCP 工具（`LOCAL_STATE_TOOL` 注解）。
- `record_progress` 工具签名加 `step_updates`。
- 更新 `MCP_INSTRUCTIONS`。

### trigger.py

- `build_trigger_input` 的 Completion contract 段替换为新措辞。

### api/routes/runs.py

- `_run_detail` 增加 `"plan": store.get_plan(run_id)`。

## 测试

- store：`record_plan` 创建/替换；`record_progress` 带 step_updates 翻转状态、忽略未知 id；plan 在 run detail 中可见；callback 校验照旧。
- web api：`/api/runs/{id}` 返回 plan；SSE 推送 plan 更新（已有 SSE 测试模式可复用）。
- trigger：`build_trigger_input` 含新 prompt 文案（含 record_plan、盲区说明）。
- 既有测试不破坏：旧式 `record_progress(message=...)` 无 step_updates 仍正常。

## 未决 / 下一轮

- follow-up 回答 `ask_user` 的 Composer 交互（设计文档原有，前端未做）——本轮不含。
- plan 步骤的嵌套（子步骤树）——YAGNI，先扁平。
- companion window 入口——已砍，靠 Chrome split view。
