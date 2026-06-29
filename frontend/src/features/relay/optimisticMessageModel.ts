export type OptimisticMessage = {
  id: string
  text: string
}

export type OptimisticMessageBuckets = Record<string, OptimisticMessage[]>

export function getOptimisticMessagesForConversation(
  buckets: OptimisticMessageBuckets,
  conversationId: number | null | undefined,
): OptimisticMessage[] {
  if (conversationId == null) return []
  return buckets[String(conversationId)] ?? []
}

export function addOptimisticMessage(
  buckets: OptimisticMessageBuckets,
  conversationId: number,
  text: string,
  createId: () => string,
): OptimisticMessageBuckets {
  const trimmed = text.trim()
  if (!trimmed) return buckets
  const key = String(conversationId)
  return {
    ...buckets,
    [key]: [...(buckets[key] ?? []), { id: createId(), text: trimmed }],
  }
}

export function removeOptimisticMessage(
  buckets: OptimisticMessageBuckets,
  conversationId: number,
  id: string,
): OptimisticMessageBuckets {
  const key = String(conversationId)
  const nextMessages = (buckets[key] ?? []).filter((message) => message.id !== id)
  if (nextMessages.length === 0) {
    const nextBuckets = { ...buckets }
    delete nextBuckets[key]
    return nextBuckets
  }
  return { ...buckets, [key]: nextMessages }
}
