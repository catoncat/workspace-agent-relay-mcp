import { mergeQueuedMessages, type QueuedComposerMessage } from './queueModel.ts'
import type { SendIntent } from './sendIntent.ts'

export type ComposerSendPlan =
  | { action: 'ignore' }
  | { action: 'queue'; text: string; conversationId: number }
  | { action: 'create_run'; text: string; conversationId: number }
  | { action: 'steer'; text: string; conversationId: number; runId: number }

export type QueueFlushPlan =
  | { action: 'ignore' }
  | { action: 'wait' }
  | {
      action: 'flush'
      conversationId: number
      text: string
      messages: QueuedComposerMessage[]
    }

export function planComposerSend({
  text,
  intent,
  conversationId,
  agentWorking,
  sending,
  localDispatchPending,
  steerTargetRunId,
}: {
  text: string
  intent: SendIntent
  conversationId: number | null | undefined
  agentWorking: boolean
  sending: boolean
  localDispatchPending: boolean
  steerTargetRunId: number | null | undefined
}): ComposerSendPlan {
  const trimmed = text.trim()
  if (!trimmed || conversationId == null) return { action: 'ignore' }
  if (intent === 'steer' && steerTargetRunId != null) {
    return {
      action: 'steer',
      text: trimmed,
      conversationId,
      runId: steerTargetRunId,
    }
  }
  if (agentWorking || sending || localDispatchPending) {
    return { action: 'queue', text: trimmed, conversationId }
  }
  return { action: 'create_run', text: trimmed, conversationId }
}

export function planQueueFlush({
  flushConversationId,
  activeConversationId,
  agentWorking,
  sending,
  localDispatchPending,
  queuedMessages,
}: {
  flushConversationId: number | null
  activeConversationId: number | null | undefined
  agentWorking: boolean
  sending: boolean
  localDispatchPending: boolean
  queuedMessages: QueuedComposerMessage[]
}): QueueFlushPlan {
  if (flushConversationId === null) return { action: 'ignore' }
  if (flushConversationId !== activeConversationId) return { action: 'wait' }
  if (agentWorking || sending || localDispatchPending) return { action: 'wait' }
  if (queuedMessages.length === 0) return { action: 'ignore' }

  const text = mergeQueuedMessages(queuedMessages)
  if (!text) return { action: 'ignore' }
  return {
    action: 'flush',
    conversationId: flushConversationId,
    text,
    messages: queuedMessages,
  }
}

export function restoreFailedFlush(
  flushedMessages: QueuedComposerMessage[],
  currentQueue: QueuedComposerMessage[],
): QueuedComposerMessage[] {
  return [...flushedMessages, ...currentQueue]
}
