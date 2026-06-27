export function buildConversationKey(name: string): string {
  const slug =
    name
      .trim()
      .toLowerCase()
      .replace(/[^\p{L}\p{N}]+/gu, '-')
      .replace(/^-|-$/g, '') || 'thread'
  return `${slug}-${Date.now().toString(36)}`
}

export function defaultConversationName(): string {
  return 'New conversation'
}
