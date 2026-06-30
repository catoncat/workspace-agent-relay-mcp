import type { LocalContext, SelectedFileContext } from '@/api/types'

export type QueuedComposerMessage = {
  id: string
  text: string
  localContext?: LocalContext
}

export type QueuedMessageBuckets = Record<string, QueuedComposerMessage[]>

const MAX_SELECTED_FILES = 20

export function getQueuedMessagesForConversation(
  buckets: QueuedMessageBuckets,
  conversationId: number | null | undefined,
): QueuedComposerMessage[] {
  if (conversationId == null) return []
  return buckets[String(conversationId)] ?? []
}

export function updateQueuedMessagesForConversation(
  buckets: QueuedMessageBuckets,
  conversationId: number,
  update: (queue: QueuedComposerMessage[]) => QueuedComposerMessage[],
): QueuedMessageBuckets {
  const key = String(conversationId)
  const nextQueue = update(buckets[key] ?? [])
  if (nextQueue.length === 0) {
    const nextBuckets = { ...buckets }
    delete nextBuckets[key]
    return nextBuckets
  }
  return { ...buckets, [key]: nextQueue }
}

export function appendQueuedMessage(
  queue: QueuedComposerMessage[],
  text: string,
  createId: () => string,
  localContext?: LocalContext,
): QueuedComposerMessage[] {
  const trimmed = text.trim()
  if (!trimmed) return queue
  const normalizedContext = normalizeLocalContext(localContext)
  return [
    ...queue,
    {
      id: createId(),
      text: trimmed,
      ...(normalizedContext ? { localContext: normalizedContext } : {}),
    },
  ]
}

export function editQueuedMessage(
  queue: QueuedComposerMessage[],
  id: string,
  text: string,
): QueuedComposerMessage[] {
  const trimmed = text.trim()
  if (!trimmed) return queue
  return queue.map((message) => (message.id === id ? { ...message, text: trimmed } : message))
}

export function removeQueuedMessage(
  queue: QueuedComposerMessage[],
  id: string,
): QueuedComposerMessage[] {
  return queue.filter((message) => message.id !== id)
}

export function takeQueuedMessage(
  queue: QueuedComposerMessage[],
  id: string,
): { message: QueuedComposerMessage | null; queue: QueuedComposerMessage[] } {
  const message = queue.find((item) => item.id === id) ?? null
  if (!message) return { message: null, queue }
  return {
    message,
    queue: removeQueuedMessage(queue, id),
  }
}

export function mergeQueuedMessages(queue: QueuedComposerMessage[]): string {
  return queue.map((message) => message.text.trim()).filter(Boolean).join('\n\n')
}

export function mergeQueuedLocalContext(queue: QueuedComposerMessage[]): LocalContext | undefined {
  return normalizeLocalContext({
    selected_files: queue.flatMap((message) => message.localContext?.selected_files ?? []),
  })
}

export function normalizeLocalContext(localContext?: LocalContext | null): LocalContext | undefined {
  const selectedFiles = localContext?.selected_files ?? []
  const normalizedFiles: SelectedFileContext[] = []
  const seenPaths = new Set<string>()

  for (const file of selectedFiles) {
    const path = file.path.trim()
    if (!path || seenPaths.has(path)) continue
    seenPaths.add(path)
    const relativePath = file.workspace_relative_path?.trim()
    normalizedFiles.push(
      relativePath ? { path, workspace_relative_path: relativePath } : { path },
    )
    if (normalizedFiles.length >= MAX_SELECTED_FILES) break
  }

  return normalizedFiles.length > 0 ? { selected_files: normalizedFiles } : undefined
}
