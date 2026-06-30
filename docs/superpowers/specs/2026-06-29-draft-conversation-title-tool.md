# 2026-06-29 Draft Conversation And Title Tool

## 背景

当前 dashboard 的“新建对话”会立即创建 conversation；同时切换到一个没有对话的 workspace 时，界面缺少明确的无选中聊天态，容易残留旧对话的上下文感。新的交互应把“新建对话”和“无选中对话”统一成一个可输入的空聊天态。

## 决策

1. 点击 New thread 只进入空聊天态并聚焦 composer，不立即写入 conversation。
2. 用户在空聊天态发送首条消息时，才创建 conversation 和第一条 run。
3. 默认 conversation 标题使用短时间戳，作为 agent 更新标题前的 fallback。
4. Relay MCP 新增 `update_conversation_title` 工具，agent 在新 conversation 的首轮任务中应调用它，把标题更新为不超过 15 个字符的短标题。
5. 标题更新通过 callback 的 `request_id + conversation_key` 校验，只能更新当前 run 所属 conversation。

## 前端行为

- `/` 路由表示没有选中 conversation 的空聊天态。
- 切换到没有 conversation 的 workspace 时停留在 `/`，显示空聊天态，不展示旧 workspace 的 conversation。
- composer 在空聊天态可输入并自动聚焦。
- 首次发送成功后跳转到新创建的 `/c/:conversationId/r/:runId`。

## 协议行为

- `update_conversation_title(request_id, conversation_key, title)` 返回更新后的 conversation。
- `title` 去除首尾空白后必须非空，长度必须小于等于 15 个字符。
- 工具写入一个内部 `conversation_title` event，供前端 stream 收到后同步本地 bootstrap cache。
- `trigger.py`、`server.py`、`docs/agent-instructions.md` 都应提示首轮标题工具用法。

## 验证

- 后端 MCP callback 测试覆盖标题更新成功、长度校验、server_info 工具列表。
- Trigger payload 测试覆盖首轮提示包含 `update_conversation_title`。
- 前端 build 覆盖 TS 类型和空聊天态 wiring。
