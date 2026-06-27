# Relay Steer 协议：追加消息续同一 Turn

日期：2026-06-27
状态：落地中（Phase 2 的 follow-up / steer 从未决转为实现；同日追加：`ask_user` 回答改为 steer 续同 turn）。

相关既有 spec：

- [2026-06-27-relay-turn-plan-semantics.md](./2026-06-27-relay-turn-plan-semantics.md) — Turn / Plan / Outcome 语义；本 spec 落地其 Phase 2 未决项第 1 条「Follow-up 是否续同一 turn」。
- [2026-06-26-workspace-agent-relay-mcp-design.md](./2026-06-26-workspace-agent-relay-mcp-design.md) — run / event / trigger 基础模型。

## 背景

落地 `superseded` 终态后，dashboard 每条 composer 消息都走 `create_run` → 自动把同 conversation 仍 active 的旧 run 标 `superseded`。用户反馈：

- 追加消息**本意是给当前 turn 加指导**（「你没 push」），不是终止旧任务开新 turn。
- Agent 侧靠 `conversation_key` 上下文连续，**仍记得要 push**——说明 ChatGPT 侧并未「终止」，只是 relay 把旧 run 关了。
- UI 暴露 `Superseded` / `Waiting` / `Accepted` 等内部状态，体感像 run 监控台，不像对话。

根因：relay 把「追加消息」一律当「新 turn」，而成熟交互（Codex `turn/steer`）里，turn 未结束时的追加输入是 **steer**，续同一 turn。

## 决策

| 场景 | 行为 |
|------|------|
| 当前 conversation **有 active run**（agent 工作中）→ composer 发送 | **steer**：同一 run，轮换 `callback_token`，追加 `user_message` 事件，用**同一 `request_id`** 重新 trigger |
| 当前 conversation **无 active run**（空闲 / 已终态）→ composer 发送 | **create_run**：新 turn，新 `request_id` + 新 token |
| Steer 后 agent 收到追加指令 | 按 [agent-instructions](../../agent-instructions.md) 第 8 条：`record_plan` 修订或 `step_updates` 标 `skipped`，**不开新 turn，不用 `record_result` 表方向变化** |
| 旧 token 的迟到回调 | `_validate_callback_conn` 因哈希不匹配拒为 `invalid_callback_token` |

## 关键约束：callback_token 不可逆

`callback_token` 以 **SHA-256 哈希**存储（`_hash_token`），不可还原明文。因此 steer **不能复用旧 token**——必须**轮换**：

1. 生成新 `callback_token` 明文。
2. `UPDATE runs SET callback_token_hash = hash(new)`。
3. 把新明文放进 steer trigger input 的 header。
4. Agent 收到后用新 token 回调，`_validate_callback_conn` 比对新哈希通过。
5. 旧 token 失效（哈希不匹配）。

`request_id` **不变**：保持同一 turn 身份；agent 的 `get_run_context` / `record_plan` / `record_progress` / `record_result` 全部落到同一 run 行。

## 风险与取舍

- **Mid-turn 旧 token 在飞回调被拒**：steer 瞬间若 agent 恰有旧 token 回调在飞，会被 `invalid_callback_token` 拒。steer 是用户主动、低频操作，且 agent 随即切到新 token，影响窗口极小。可接受；前端不为此特殊提示。
- **`superseded` 状态保留**：`create_run` 的自动 supersede 逻辑不删，作为安全网（异常多 active run / 旧数据）。steer 路径下正常流程不再触发它。UI 不再对 `superseded` 特殊渲染，仅作 frozen 过去 turn。
- **不引入「新任务」按钮**：单一 composer 输入；agent 据 steer trigger 文案自决重做（skip 旧步 + 新 plan）或修订。若用户真要全新任务，等当前 turn `record_result` 终态后再发即自然开新 turn。
- **竞态**：前端据 SSE 的 `latestRunStatus` 分流 steer/create；若状态过期（run 已终态）仍调 steer，后端返 409，前端自动 fallback 到 `createRun`。

## 触发口径同步

按仓库 `AGENTS.md` §2，三处口径必须一致：

- `src/workspace_agent_relay_mcp/trigger.py` — `build_trigger_input(mode="steer")` 正文。
- `src/workspace_agent_relay_mcp/server.py` — `MCP_INSTRUCTIONS`。
- `docs/agent-instructions.md` — 第 8 条追加 steer 句。

## ask_user 回答：续同 turn 而非开新 turn（2026-06-27 追加）

steer 落地后浮现的 Phase 2 未决项：`ask_user` 把 run 置 `needs_user` 后，操作者回答应**续同一 turn**，而非像旧实现那样 `create_run` 开新 turn 再把提问 run `supersede`。`needs_user` 是活跃、非终态 run，符合 steer 前提，故回答直接走 steer。

| 场景 | 行为 |
|------|------|
| Agent `ask_user` → run `needs_user` → composer 发送 / 点选项 | **steer（answer 变体）**：同一 run，轮换 token，追加 `user_message`，同 `request_id` 重 trigger；trigger 文案用「Operator answered:」+「resume the turn」框架 |
| steer_run 对 `needs_user` run | 轮换 token + 追加 `user_message` + **状态 `needs_user` → `sent`**（回答=恢复，离开提问态）；随后 `update_run_trigger_result` 把 `sent` → `accepted`（agent 恢复中） |
| 其它 active 状态（running / progress / accepted / waiting）的 steer | 状态**不变**（agent 仍在工作，steer 是追加指导，不是恢复） |
| 旧 token 迟到回调 | `invalid_callback_token`（同通用 steer） |

关键状态机修正：`update_run_trigger_result` 只在 `TRIGGER_MUTABLE_RUN_STATUSES = {draft, sent}` 时改状态；若 steer_run 不把 `needs_user` 重置为 `sent`，run 会**卡在 `needs_user`**——UI 仍显示「可回答」、选项仍可点、可重复回答。故 `steer_run` 在 run 处于 `USER_REPLY_STATUSES = {needs_user, question, ask_user}` 时显式置 `sent`，由后续 trigger 结果推进到 `accepted`。

新增常量 `USER_REPLY_STATUSES`（`store/relay_store.py`，经 `db.py` re-export）；`build_trigger_input` 新增 `answer: bool` 参数；steer 路由按 `active["status"] ∈ USER_REPLY_STATUSES` 传 `answer=True`。

触发口径同步（同上三处，本次更新点）：

- `trigger.py` — `build_trigger_input(mode="steer", answer=True)` 的「Operator answered:」正文。
- `server.py` — `MCP_INSTRUCTIONS` 的 ask_user 句接上「回答以 steer 续同 turn」。
- `docs/agent-instructions.md` — 第 7 条 + 第 9 条 +「Blocking Questions」节均补「回答=steer、`Operator answered:`、续同 turn」。

## UI 对齐

- 删 `SupersededRunSummary` 折叠卡；`superseded` run 走正常 `RunThread`（plan frozen、progress 照常），无虚线框、无「folded into…」文案。
- `StatusBadge` 仅在 `shouldShowHeaderStatusBadge`（`failed` / `blocked` / `needs_user` / `question` / `ask_user` / `trigger_failed`）时显示；进行中 / done / superseded 不出 badge。
- 去 `Turn N · follow-up` 标签噪音。
- `RunPhaseHint` 仅在「trigger 已发但无任何 event/plan」时短暂显示。
- `user_message` 事件作为用户气泡内联渲染，让 steer 追加消息像聊天一样出现在 agent 进度之间。
- composer 新增 `replying` 模式：run `needs_user` 时 placeholder 显示「Answer the agent…」、发送键 aria-label「Send answer」；发送路由经 `shouldSteerLatestRun`（`isComposerBusy || isUserReplyStatus`）走 steer，而非旧的 `createRun`。回答后 run 离开 `needs_user` → `accepted`，`QuestionEvent` 选项自动失效，避免重复回答。

## 验证清单

- 后端 `pytest tests/ -q` 全绿（含 `test_steer_run_*` / `test_steer_route_*` / `test_steer_input_*`）。
- 前端 `npm run build` 零错误。
- 端到端（须真实 Workspace Agent，`callback_token` 哈希不可伪造）：run A 进行中发追加「你没 push」→ A 仍 active、新增 `user_message` 事件、token 已轮换、agent 用新 token 回调且 `record_plan` 标 revised 而非新开 turn；A 完成后 `record_result(done)`。
- 端到端 ask_user 回答：run A 中 agent `ask_user` → A 变 `needs_user`、composer 切 `replying`；操作者点选项 / 输入回答 → 走 steer（同 A、token 轮换、`user_message` 气泡、trigger 文案「Operator answered:」）→ A 离开 `needs_user` 进 `accepted`、选项失效；agent 用新 token 续同 turn 完成 `record_result(done)`。

## 变更记录

- **2026-06-27**：初稿。落地 Phase 2 steer：token 轮换 + `user_message` 事件 + 同 `request_id` 重 trigger + UI 对话化。
- **2026-06-27（追加）**：`ask_user` 回答改为 steer 续同 turn。新增 `USER_REPLY_STATUSES`；`steer_run` 对 `needs_user` run 置 `sent`（修复「卡在 needs_user 可重复回答」）；`build_trigger_input(answer=True)` 「Operator answered:」文案；steer 路由按状态传 `answer`；三处口径同步；前端 `shouldSteerLatestRun` 路由 + composer `replying` 模式。
