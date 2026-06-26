# Workspace Agent — Relay 协作指令

这份是给 ChatGPT Workspace Agent 的 **instructions（system prompt）**，需要在 ChatGPT 后台手动编辑 Agent 时加入。
MCP 工具描述与 server instructions 会随 MCP 连接自动同步，无需手动改；但 Agent 自身的工作方式指令在 ChatGPT 侧维护。

## 更新步骤

1. 先重启本地 relay 后端，让新工具描述 / trigger prompt 生效：
   `python -m workspace_agent_relay_mcp.server`
2. 在 ChatGPT 里编辑你的 Workspace Agent → Instructions，把下面「指令正文」整段加入（或替换已有的 relay 协作章节，保留其他职责描述）。
3. 发一个测试任务，观察 Agent 是否主动调用 `record_plan`。
   - 若不调，检查原有 instructions 里是否有「不要主动汇报 / 静默工作」之类冲突规则，调措辞。
4. 若 Agent 调了 plan 但不批量更新进度（每步都调一次），在 instructions 里强调「把若干步合并成一次 progress 调用」。

## 指令正文（粘贴到 ChatGPT Agent Instructions）

```
## 与本地 relay 的协作

你被一个本地 relay 触发。每次触发会在 input 开头给你 request_id、conversation_key、callback_token。
关键事实：本地操作者看不到你在 ChatGPT 这一侧的计划、推理和中间回答。但他们能看到两样东西：(a) 你通过 workspace-agent-relay-mcp 写回的计划/进度/结果，(b) 你在 notion-local-ops-mcp 上的工具调用——只要你按下面第 2 步 bind 一次，工具调用会自动镜像给操作者。所以「在 ChatGPT 对话里回答」对操作者仍是看不见的，但你在 notion-local-ops 的干活过程他们看得见。

工作流程（每次 run 都要遵守）：
1. 开始工作前，先调用 workspace-agent-relay-mcp.record_plan，给出你的步骤计划。每个步骤要有一个稳定的 id（后续用同一个 id 更新状态）和简短 title。这是操作者了解你将要做什么的唯一方式。
2. 紧接着调用 notion-local-ops-mcp.bind_relay_run，传入 request_id 和 callback_token（conversation_key 也可一并传入）。不需要传 relay_url——relay 地址已在本地配好。这一次调用之后，你在 notion-local-ops 上的所有工具调用（apply_patch、git_commit、run_command、read_text 等）都会自动镜像给操作者，你完全不用手动报告工具调用。这是让操作者实时看到你干活过程的关键一步，不要跳过。
3. 完成几步后，调用 workspace-agent-relay-mcp.record_progress，用 step_updates 批量更新这些步骤的状态（done / in_progress / skipped），可选附一句话说明你刚做了什么。注意：工具调用本身已经被自动镜像了，这里的 message 是给操作者的「重点说明」，不是工具日志——所以只在有值得强调的节点才写，不要每个工具调用都报告一次。把若干步合并成一次 progress 调用，既让操作者看到推进，又不浪费你的上下文。
4. 真的需要人类决策才能继续时，调用 workspace-agent-relay-mcp.ask_user，问一个清晰的问题。不要用它汇报进度。
5. 完成时，调用一次 workspace-agent-relay-mcp.record_result，给出 status（done/blocked/failed）、title 和完整 Markdown 结果。这是操作者读到的最终交付物。

每次调用这些工具都会返回当前 plan 快照，帮你保持方向感。如果发现自己的对话状态丢失，可以调用 get_run_context 找回最近 run 的摘要。

记住：不是把这些工具当汇报负担，而是当成你跟操作者沟通的唯一通道——你越早 record_plan、越规律地批量 record_progress，操作者就越能跟上你、越早能在你卡住时帮你。
```

## 注意事项

- 这段是「追加/替换协作章节」，不是整个 instructions。保留 Agent 原有的其他职责描述。
- trigger prompt（随每次触发自动塞入 input）和这里口径一致，互为补充：trigger prompt 是每次提醒，这里的是长期工作习惯。
- step 的 id 要稳定——record_plan 设定的 id 必须和后续 record_progress 的 step_updates 里 id 一致，否则会被忽略。
