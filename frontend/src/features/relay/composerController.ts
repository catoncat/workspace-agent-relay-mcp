import type { LocalContext } from '@/api/types'
import {
  mergeQueuedLocalContext,
  mergeQueuedMessages,
  normalizeLocalContext,
  type QueuedComposerMessage,
} from './queueModel.ts'
import type { SendIntent } from './sendIntent.ts'

export type ComposerSendPlan =
  | { action: 'ignore' }
  | { action: 'queue'; text: string; conversationId: number; localContext?: LocalContext }
  | { action: 'create_run'; text: string; conversationId: number; localContext?: LocalContext }
  | { action: 'steer'; text: string; conversationId: number; runId: number; localContext?: LocalContext }

export type QueueFlushPlan =
  | { action: 'ignore' }
  | { action: 'wait' }
  | {
      action: 'flush'
      conversationId: number
      text: string
      localContext?: LocalContext
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
  localContext,
}: {
  text: string
  intent: SendIntent
  conversationId: number | null | undefined
  agentWorking: boolean
  sending: boolean
  localDispatchPending: boolean
  steerTargetRunId: number | null | undefined
  localContext?: LocalContext
}): ComposerSendPlan {
  const trimmed = text.trim()
  if (!trimmed || conversationId == null) return { action: 'ignore' }
  const normalizedContext = normalizeLocalContext(localContext)
  if (intent === 'steer' && steerTargetRunId != null) {
    return {
      action: 'steer',
      text: trimmed,
      conversationId,
      runId: steerTargetRunId,
      ...(normalizedContext ? { localContext: normalizedContext } : {}),
    }
  }
  if (agentWorking || sending || localDispatchPending) {
    return {
      action: 'queue',
      text: trimmed,
      conversationId,
      ...(normalizedContext ? { localContext: normalizedContext } : {}),
    }
  }
  return {
    action: 'create_run',
    text: trimmed,
    conversationId,
    ...(normalizedContext ? { localContext: normalizedContext } : {}),
  }
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
  const localContext = mergeQueuedLocalContext(queuedMessages)
  return {
    action: 'flush',
    conversationId: flushConversationId,
    text,
    ...(localContext ? { localContext } : {}),
    messages: queuedMessages,
  }
}

export function restoreFailedFlush(
  flushedMessages: QueuedComposerMessage[],
  currentQueue: QueuedComposerMessage[],
): QueuedComposerMessage[] {
  return [...flushedMessages, ...currentQueue]
}
