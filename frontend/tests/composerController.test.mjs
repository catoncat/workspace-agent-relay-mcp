import test from 'node:test'
import assert from 'node:assert/strict'

import {
  planComposerSend,
  planQueueFlush,
  restoreFailedFlush,
} from '../src/features/relay/composerController.ts'

test('rapid normal sends use local dispatch pending to queue the second message', () => {
  assert.deepEqual(
    planComposerSend({
      text: ' first ',
      intent: 'queue',
      conversationId: 101,
      agentWorking: false,
      sending: false,
      localDispatchPending: false,
      steerTargetRunId: null,
    }),
    { action: 'create_run', text: 'first', conversationId: 101 },
  )

  assert.deepEqual(
    planComposerSend({
      text: ' second ',
      intent: 'queue',
      conversationId: 101,
      agentWorking: false,
      sending: false,
      localDispatchPending: true,
      steerTargetRunId: null,
    }),
    { action: 'queue', text: 'second', conversationId: 101 },
  )
})

test('send plan preserves selected file context for create run and steer', () => {
  const localContext = {
    selected_files: [
      { path: '/repo/src/app.py', workspace_relative_path: 'src/app.py' },
    ],
  }

  assert.deepEqual(
    planComposerSend({
      text: ' inspect this ',
      intent: 'queue',
      conversationId: 101,
      agentWorking: false,
      sending: false,
      localDispatchPending: false,
      steerTargetRunId: null,
      localContext,
    }),
    {
      action: 'create_run',
      text: 'inspect this',
      conversationId: 101,
      localContext,
    },
  )

  assert.deepEqual(
    planComposerSend({
      text: ' use this context ',
      intent: 'steer',
      conversationId: 101,
      agentWorking: true,
      sending: false,
      localDispatchPending: false,
      steerTargetRunId: 55,
      localContext,
    }),
    {
      action: 'steer',
      text: 'use this context',
      conversationId: 101,
      runId: 55,
      localContext,
    },
  )
})

test('queue flush waits while busy then dispatches merged FIFO text when idle', () => {
  const queuedMessages = [
    { id: 'q1', text: 'first' },
    { id: 'q2', text: 'second' },
  ]

  assert.deepEqual(
    planQueueFlush({
      flushConversationId: 101,
      activeConversationId: 101,
      agentWorking: true,
      sending: false,
      localDispatchPending: false,
      queuedMessages,
    }),
    { action: 'wait' },
  )

  assert.deepEqual(
    planQueueFlush({
      flushConversationId: 101,
      activeConversationId: 101,
      agentWorking: false,
      sending: false,
      localDispatchPending: false,
      queuedMessages,
    }),
    {
      action: 'flush',
      conversationId: 101,
      text: 'first\n\nsecond',
      messages: queuedMessages,
    },
  )
})

test('queue flush merges selected file context in FIFO order without duplicates', () => {
  const queuedMessages = [
    {
      id: 'q1',
      text: 'first',
      localContext: {
        selected_files: [
          { path: '/repo/a.py', workspace_relative_path: 'a.py' },
          { path: '/repo/shared.py', workspace_relative_path: 'shared.py' },
        ],
      },
    },
    {
      id: 'q2',
      text: 'second',
      localContext: {
        selected_files: [
          { path: '/repo/shared.py', workspace_relative_path: 'shared.py' },
          { path: '/repo/b.py', workspace_relative_path: 'b.py' },
        ],
      },
    },
  ]

  assert.deepEqual(
    planQueueFlush({
      flushConversationId: 101,
      activeConversationId: 101,
      agentWorking: false,
      sending: false,
      localDispatchPending: false,
      queuedMessages,
    }),
    {
      action: 'flush',
      conversationId: 101,
      text: 'first\n\nsecond',
      localContext: {
        selected_files: [
          { path: '/repo/a.py', workspace_relative_path: 'a.py' },
          { path: '/repo/shared.py', workspace_relative_path: 'shared.py' },
          { path: '/repo/b.py', workspace_relative_path: 'b.py' },
        ],
      },
      messages: queuedMessages,
    },
  )
})

test('explicit steer or answer bypasses the local queue and targets the active run', () => {
  assert.deepEqual(
    planComposerSend({
      text: ' answer ',
      intent: 'steer',
      conversationId: 101,
      agentWorking: true,
      sending: false,
      localDispatchPending: false,
      steerTargetRunId: 55,
    }),
    { action: 'steer', text: 'answer', conversationId: 101, runId: 55 },
  )
})

test('failed queue flush restores unsent messages before newer queued input', () => {
  const flushed = [
    { id: 'q1', text: 'first' },
    { id: 'q2', text: 'second' },
  ]
  const current = [{ id: 'q3', text: 'third' }]

  assert.deepEqual(restoreFailedFlush(flushed, current), [
    { id: 'q1', text: 'first' },
    { id: 'q2', text: 'second' },
    { id: 'q3', text: 'third' },
  ])
})
