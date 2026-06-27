# Relay Turn / Plan / Outcome 语义规范

日期：2026-06-27  
状态：已落地 Phase 0/1/1.5/3（superseded 终态 + 续接 trigger + UI revision/superseded）；Phase 2 留待 follow-up / steer。

## 背景

relay dashboard 在展示 plan、run 状态、result 卡片时出现概念混淆，典型症状：

1. 用户纠偏后出现 **两张 plan 卡片**，旧 plan 仍显示 `working`。
2. Agent 用 `record_result(status=blocked)` 表达「方向 pivot」，前端渲染 **Blocked 气泡**，与 plan 卡片割裂。
3. 团队内部对 **Run** 究竟代表「一次用户消息」「一次任务」还是「callback 鉴权边界」没有统一口径。

本 spec 基于对 **OpenAI Codex（App Server + CLI）**、**Cursor Plan Mode**、**Claude Code（Plan + Tasks）** 的公开文档调研，给出 relay 应采用的 **canonical 语义**，并映射到现有实现（`runs` / `plans` / `events` 表无需立即重命名）。

相关既有 spec：

- [2026-06-26-relay-plan-progress-protocol-design.md](./2026-06-26-relay-plan-progress-protocol-design.md) — plan/progress 工具与 step 状态机
- [2026-06-26-workspace-agent-relay-mcp-design.md](./2026-06-26-workspace-agent-relay-mcp-design.md) — run / event / result 基础模型

---

## 行业调研摘要

### 共识：四层分离

| 层 | 职责 | 典型生命周期 |
|----|------|--------------|
| **Thread / Session / Conversation** | 持久对话容器，跨多次用户输入保留上下文 | 长期 |
| **Turn** | **一次用户输入**触发的 agent 工作单元（含 tool loop，直到 idle / 等待用户 / 终局） | 分钟级 |
| **Plan / Todo state** | **可变**的工作意图与步骤状态；可在 turn 内修订 | turn 内为主，部分产品跨 session |
| **Item / Event** | 原子输出：message、tool call、trace、question… | 秒级 |

成熟产品 **不** 用 run/turn 的终态（blocked/failed）表示「plan 换了」。

### OpenAI Codex（Workspace Agent 同源 harness）

官方 [App Server](https://developers.openai.com/codex/app-server) 定义：

- **Thread**：用户与 agent 的持久会话，含多个 turn。
- **Turn**：一次用户请求及后续 agent 工作；含多个 item。
- **Item**：userMessage、agentMessage、commandExecution、plan…
- **`turn/plan/updated`**：agent **分享或修改 plan** 时推送；每步 `{ step, status }`，status 为 `pending | inProgress | completed`。
- **`turn/steer`**：turn 未结束时追加用户输入（mid-turn 纠偏）。
- **`turn/completed`**：status 为 `completed | interrupted | failed` — **turn 收场**，非 plan 子状态。

[Codex Prompting — Threads](https://developers.openai.com/codex/prompting) 补充：

- 同一 thread 可含 **多个 prompt**（首问 + follow-up 测例）。
- **`/goal`**：跨多步的持久目标，带 completion criteria。

### Cursor Plan Mode

[Plan Mode 文档](https://cursor.com/docs/agent/plan-mode)：

- 先产出 **可编辑 Markdown plan + todo**，人改完再 Build。
- 做错时：**revert →  refine plan → 再跑**，而非打一个终态卡片表示 pivot。

### Claude Code

[Common workflows — Plan before editing](https://code.claude.com/docs/en/common-workflows)：

- **Plan mode**：只读规划，产出 plan 文件；用户 Ctrl+G 编辑后再 implement。
- **Tasks API**（`TaskCreate` / `TaskUpdate` / `TaskList`）：`pending → in_progress → completed`，可跨 session（`CLAUDE_CODE_TASK_LIST_ID`）。
- 方向变更：改 plan / tasks 或开新 session 读 plan 文件 — **不用 failed/blocked 表示 plan 废弃**。

### 调研结论（relay 应对齐的要点）

1. **Plan 是 mutable state**，不是 turn 的静态附件。
2. **Turn** 粒度 = 一次用户输入触发的 agent 工作，**小于** conversation，**大于** 单个 tool call。
3. **Plan 修订**应产生 **revision 信号**（Codex：`turn/plan/updated`；relay 已有：`event_type=plan`）。
4. **Outcome（终态）** 与 **Plan** 正交；`blocked` 表示 turn 无法正常完成，**不** 表示「计划换了」。

---

## Relay canonical 模型

### 术语对照（产品名 ↔ 实现名）

| 产品/文档术语 | 代码/DB 现名 | 定义 |
|---------------|--------------|------|
| **Conversation（对话线程）** | `conversations` + `conversation_key` | 操作者眼中的同一课题；与 ChatGPT 侧 memory 对齐。 |
| **Turn（回合）** | `runs` 表一行 | **一次** dashboard composer 发送（或未来：同 turn 的 steer/follow-up）所触发的 agent 工作单元；含独立 `request_id` + `callback_token`。 |
| **PlanState（计划状态）** | `plans` 表 + `events.event_type=plan` | 该 turn 内 agent 声明的 **当前** 步骤状态机；**可修订**；修订历史在 `plan` 事件中。 |
| **Item（事件项）** | `events`（progress/question/…） | 比 turn 更细的原子记录；含 tool trace（`payload.trace=true`）。 |
| **Outcome（回合结局）** | `record_result` + `runs.status` 终态 | 该 turn 如何收场：`done | blocked | failed`（及无 result 的异常终态）。 |

**保留 `run` 作为工程/API 名**，对外 UI 与 agent 指令统一使用 **Turn（回合）**。

### 层级关系

```
Conversation
  └── Turn 1
        ├── input_markdown          # 本回合用户输入
        ├── PlanState (0..1 当前快照)
        │     └── revisions[]       # 来自 plan 事件历史（逻辑视图，非新表）
        ├── Items[]                 # progress, trace, question, …
        └── Outcome (0..1)          # result 事件 + 终态 status
  └── Turn 2
        └── …
```

**PlanState 从属于 Turn**，但语义上是 **可变对象**，不是「回合开始时写死的 checklist」。

### PlanState 行为（与现有协议一致，语义写清）

| 操作 | MCP 工具 | 效果 |
|------|----------|------|
| 首次声明 plan | `record_plan` | 创建 plan；写 `plan` 事件 |
| 整份修订 | `record_plan`（再次调用） | **替换** steps；写 `plan` 事件（title: "Plan updated"） |
| 逐步推进 / 跳过 | `record_progress(step_updates)` | 更新 step status/note；写 `progress` 事件 |
| 跳过剩余步骤 | `step_updates: [{id, status: "skipped"}]` | 纠偏 / 放弃某路线时的 **正道** |

step `status`：`pending | in_progress | done | skipped`（沿用 [plan-progress spec](./2026-06-26-relay-plan-progress-protocol-design.md)）。

**Plan 修订 ≡ Codex `turn/plan/updated`**。relay 已实现存储（`plan` 事件），dashboard 以 `revised` 标记（≥2 条 `plan` 事件）呈现，展示最新 snapshot。

### Outcome 行为

| status | 含义 | 谁能设置 |
|--------|------|----------|
| `done` | 本 turn 目标已交付 | agent（`record_result`） |
| `failed` | 本 turn 执行失败 | agent（`record_result`） |
| `blocked` | 本 turn 因 **外部硬阻塞** 无法继续（缺权限、缺资源、等第三方）；**不是**用户纠正方向 | agent（`record_result`） |
| `superseded` | 本 turn 被同 conversation 内更新的 turn 取代；旧 turn 的 PlanState frozen，迟到回调以 `run_closed` 拒绝 | **系统**（`create_run` 时自动设置）；agent 不可经 `record_result` 设置 |

`VALID_RESULT_STATUSES = {done, blocked, failed}`（agent 可设）；`TERMINAL_STATUSES = {done, blocked, failed, superseded}`（含系统态）。两者刻意分离，`superseded` 是系统专用。

**禁止**：用 `record_result(blocked)` 表示「plan pivot / 方向放弃 / 等用户换思路」。这些场景应使用 plan 协议或 `ask_user` / 新 turn。

### Turn 之间的关系

| 场景 | 期望行为 |
|------|----------|
| 用户 composer 发 **新消息** | 创建 **新 Turn**（`create_run`）；`create_run` 内自动把同 conversation 下仍非终态的旧 turn 标 `superseded` + 写 `system` 事件 + SSE 通知 |
| 同 turn 内 agent **修订 plan** | 仅 `record_plan` / `step_updates`；UI 显示 **plan revision**，不新开 turn |
| Agent **需要人决策** | `ask_user` → `needs_user`（**非终态**） |
| 用户 **回答** ask_user | 理想：follow-up **续同一 turn** 或显式 parent 链接；**现状**：composer 一律新 turn（见未决项） |
| 旧 turn agent **迟到回调** | 被 `_validate_callback_conn` 以 `run_closed` 拒绝（`superseded` 属终态）；不污染新 turn |

**Superseded** 由后端在 `create_run` 收口，不再依赖前端推断。旧 turn 的 PlanState 保留为 frozen 快照（plan 行不删），dashboard 显示 `Superseded` badge + plan 卡片 `superseded` 标签，无 live spinner。

---

## 与现有实现的偏差（gap list）

| # | 偏差 | 严重性 | 状态 |
|---|------|--------|------|
| G1 | UI 只渲染 `detail.plan` 快照，**忽略 `plan` 事件** | 高 | ✅ 已修：`revised` 标记（≥2 条 `plan` 事件） |
| G2 | composer 每条消息 = 新 turn，纠偏常表现为 **双 plan** | 高 | ✅ 已修：`create_run` 自动 supersede 旧 turn + UI frozen |
| G3 | `blocked` result 渲染为独立聊天气泡，易与 plan 混淆 | 中 | ✅ 已修：agent 指令禁止 blocked 表 pivot；UI 不合并 |
| G4 | 设计文档有 follow-up / `POST .../follow-up`，**未实现** | 中 | Phase 2：parent_turn_id 或 steer |
| G5 | 产品称 Run，用户心智是 Turn/Task | 低 | ✅ 已修：UI 加 `Turn N` 标签 |
| G6 | 续接消息冗余（每条 ~250 token contract） | 中 | ✅ 已修：`is_continuation` 紧凑提醒 |
| G7 | notion 掉线时 agent 易 `failed_during_run` | 中 | ✅ 已修：trigger 文本含 notion fallback |

---

## Trigger input：首次 vs 续接

`build_trigger_input(..., is_continuation=bool)` 按 conversation 是否已有 run 分两档，避免每条消息重复 ~250 token 的完整 contract：

| 档 | 内容 | 何时 |
|----|------|------|
| **首次** | 参数行 + 完整 `Completion contract`（含 Turn/Plan/Outcome 口径 + notion fallback） | 该 conversation 尚无 run |
| **续接** | 参数行 + 一行紧凑提醒 `Same relay protocol as before: record_plan → bind_relay_run → record_progress → record_result …` | 该 conversation 已有 run |

续接不发完整 contract 的折中理由：长会话上下文压缩可能弱化早期协议指令，故仍保留**一行续命提醒**而非完全静默。

### notion-local-ops-mcp fallback

首续两档都带：`If notion-local-ops-mcp is unavailable, skip bind_relay_run and still call record_progress/record_result so the operator stays informed.`

意图：agent 掉 notion 连接时**降级只走 relay 回调**，不因 bind 失败而 `failed_during_run`；操作者至少仍能看到 plan/progress/result。

### 续接判定

`routes/runs.py` 在 `build_trigger_input` 前调 `list_runs_for_conversation`：长度 > 0 即续接。新 run 尚未插入，判定无歧义。

---

## Agent 指令口径（三处须同步）

变更时同步：`trigger.py`（Completion contract）、`server.py`（`MCP_INSTRUCTIONS`）、`docs/agent-instructions.md`。

### Turn 与 Plan

- 每次 trigger 对应 **一个 turn**（一个 `request_id` / `callback_token`）。
- 在本 turn 内，**先** `record_plan`；方向变化时 **再次** `record_plan` 或 `step_updates: skipped`，**不要**用 `record_result` 说明 pivot。
- `record_progress` 批量更新 step；工具细节靠 notion-local-ops trace，勿逐步 narration。

### Outcome 选用

| 情况 | 调用 |
|------|------|
| 本 turn 任务完成 | `record_result(status=done, …)` |
| 执行错误 | `record_result(status=failed, …)` |
| 外部依赖阻塞，本 turn 无法继续 | `record_result(status=blocked, …)` |
| 需要人选择才能继续 | `ask_user`（**不要** blocked） |
| 用户已在新消息里纠正方向 | 在新 turn 上 `record_plan`；旧 turn 剩余 step 标 `skipped`（若仍回调旧 token）或 **不要** 对旧 turn 写 result |

### 与 ChatGPT 记忆

- 同一 `conversation_key` 下 ChatGPT 可跨 turn 保留记忆；relay turn 是 **回调边界**，不等于 ChatGPT thread 的每一跳。
- Agent 应用 `get_run_context` 对齐最近 turn 摘要，避免重复 plan 已 abandoned 的方向。

---

## Dashboard UI 规范

### Turn 块结构（时间正序）

1. **用户消息**（`input_markdown`）
2. **PlanState 卡片**（若有 plan）
3. **Items**：tool traces、progress narration、question…
4. **Outcome**（若有 result；或无 result 的 terminal 提示）

### PlanState 卡片状态机（UI）

| UI 状态 | 条件 |
|---------|------|
| **live** | 本 turn 是 conversation 内 **authoritative active turn**（最新 active 且有 plan） |
| **superseded** | `run.status === 'superseded'`（后端在 `create_run` 时设置） |
| **frozen** | 本 turn 已 outcome 或已 superseded；step 无 spinner |
| **revised** | 本 turn 有 ≥2 条 `plan` 事件；展示最新 snapshot，可选展开 revision |

UI 的 `planSuperseded` 以 `run.status === 'superseded'` 为准（后端真实状态），兼容保留「active 但非 authoritative」的窗口推断。

**禁止**：因 `outcome=blocked` 将 result 合并进 plan 卡片（无协议字段关联）。

### Sticky plan bar

- 仅当 authoritative turn 的 plan 卡片 **滚出视口** 时显示 compact 摘要（已实现方向）。
- 点击滚回 plan 锚点，非 run 顶。

### 文案

- 界面：**Turn** / **回合**（避免仅写 Run）。
- Header badge 仍可用 run.status，但 help text 解释其为 turn 状态。

---

## 数据模型：暂不迁移

本 spec **不要求**立即改表名或把 plan 升到 conversation 级。

理由（对齐 Codex）：

- Codex 的 plan 更新发生在 **turn 内**（`turn/plan/updated`），不是 thread 级单例。
- Claude **跨 session** 的 Tasks 是增强层；relay MVP 可先做好 **turn 内 revision + superseded**。

若未来需要 conversation 级 PlanState（长课题、多 turn 共享路线图），另开 spec，引入 `conversation_plans` 或 `plan.conversation_id` — **不在本 spec 范围**。

---

## 实施阶段

### Phase 0 — 文档与指令（本 spec 合并后）

- [x] 评审本 spec
- [x] 同步 `trigger.py` / `MCP_INSTRUCTIONS` / `docs/agent-instructions.md` 中 Turn/Plan/Outcome 口径
- [x] 在 [AGENTS.md](../../../AGENTS.md) 或 plan-progress spec 加交叉引用

### Phase 1 — UI（无协议变更）

- [x] Plan 卡片：authoritative / superseded / frozen
- [x] 消费 `plan` 事件：`revised` 标记
- [x] Turn 标签（「回合 2」）与 conversation 叙事主轴
- [x] 不合并 blocked result 入 plan
- [x] Sticky plan bar 仅在 plan 卡片滚出视口时显示（IntersectionObserver）

### Phase 1.5 — 后端收口（原 gap list G2/G6/G7）

- [x] `superseded` 升格为真实终态（`TERMINAL_STATUSES`，系统设置）
- [x] `record_result` 拒绝 `superseded`（`VALID_RESULT_STATUSES` 与终态分离）
- [x] `create_run` 内清理僵尸 turn（标 superseded + `system` 事件 + SSE 通知）
- [x] `build_trigger_input(is_continuation)` + notion fallback 文本
- [x] `routes/runs.py` 续接判定

### Phase 2 — 产品/协议可选增强

- [ ] Follow-up turn：`parent_run_id` 或 dedicated follow-up API（设计文档已有雏形）
- [ ] Mid-turn steer：同一 `request_id` 接受第二次 trigger input（需安全模型评审）
- [ ] `get_run_context` 返回 active/superseded 提示供 agent 自检

### Phase 3 — 观测与测试

- [x] store 测试：plan 事件序列与 snapshot 一致
- [x] store 测试：`create_run` 自动 supersede 旧 turn + 迟到回调被拒
- [x] store 测试：`record_result` 拒绝 `superseded`
- [x] trigger 测试：续接消息紧凑且含 notion fallback；首次含完整 contract
- [x] 前端 build 门槛
- [x] 端到端（2026-06-27，agent `second` / conv 6）：run A 触发后 8s 发 run B 方向纠正 → A 自动 `superseded` + `system` 事件；B `record_plan`（1 步「已取消旧任务」）+ `record_result(done)`，**未** 用 `blocked`，**未** bind/执行 date。验证续接紧凑 contract + 僵尸清理 + 新方向走 plan 而非 blocked。

---

## 场景走查

### A. Turn 内 plan 修订（同 request_id）

1. 用户：「用本地桥部署」
2. Agent：`record_plan` 5 步
3. 用户 **在 ChatGPT 内**纠正：「不要本地桥」
4. Agent：`record_plan` 4 步（新方向）+ 可选 skip 旧步
5. UI：同一 turn **一条 plan 卡片**，标 `revised`；**无** Blocked outcome

### B. 新 composer 消息（新 turn）

1. Turn 1 plan 进行中
2. 用户 dashboard 发纠正消息 → `create_run` 创建 Turn 2；**后端**自动把 Turn 1 标 `superseded` + 写 `system` 事件
3. Turn 1 plan → **superseded/frozen**（`run.status` 驱动）；Turn 2 新 `record_plan`
4. Turn 1 agent 若迟到回调 → `_validate_callback_conn` 以 `run_closed` 拒绝
5. Agent **不应** Turn 1 `record_result(blocked)` 写 pivot 小作文（即便写了，迟到回调也已被拒）

### C. 真实 blocked

1. Agent 需要生产 API key，用户未配置
2. Agent：`record_result(status=blocked, title="Missing API key", …)`
3. UI：Turn 块底部 **Outcome 卡片**（与 plan 分离）；plan 显示 frozen，未完成 step 可保留 pending/skipped

### D. ask_user

1. Agent：`ask_user` → turn `needs_user`
2. 用户 composer 回答 → **现实现** 新 turn；UI 应能关联 question 与下一 turn（Phase 2）

---

## 未决项

1. **Follow-up 是否续同一 turn** — 涉及 callback_token 生命周期；默认 Phase 2 再定。
2. **Plan revision UI 深度** — 仅「已修订」badge vs 完整 diff 时间线。
3. **Conversation 级 plan** — 仅当多 turn 长课题被验证为刚需时再 spec。

---

## 参考链接

- [Codex App Server — Thread / Turn / Item](https://developers.openai.com/codex/app-server)
- [Codex Prompting — Threads, Goal mode](https://developers.openai.com/codex/prompting)
- [Unlocking the Codex harness (App Server 架构)](https://openai.com/index/unlocking-the-codex-harness/)
- [Cursor Plan Mode](https://cursor.com/docs/agent/plan-mode)
- [Claude Code — Common workflows (Plan before editing)](https://code.claude.com/docs/en/common-workflows)
- [Introducing workspace agents in ChatGPT](https://openai.com/index/introducing-workspace-agents-in-chatgpt/)（Codex 驱动）

---

## 变更记录

- **2026-06-27**：初稿。调研 Codex / Cursor / Claude Code；定义 Turn / PlanState / Outcome；列出 gap 与 phased rollout。
- **2026-06-27（同步）**：落地 Phase 0/1/1.5/3 后回填——`superseded` 升格为后端真实终态（系统设置，`record_result` 不可设）；`create_run` 自动清理僵尸 turn；`build_trigger_input(is_continuation)` 分首续两档并加 notion-local-ops-mcp fallback；UI `planSuperseded` 改由 `run.status` 驱动，`revised` 标记消费 `plan` 事件；gap list G1/G2/G3/G5/G6/G7 标记已修。
