export type QueuedComposerMessage = {
  id: string
  text: string
}

export type QueuedMessageBuckets = Record<string, QueuedComposerMessage[]>

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
): QueuedComposerMessage[] {
  const trimmed = text.trim()
  if (!trimmed) return queue
  return [...queue, { id: createId(), text: trimmed }]
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
