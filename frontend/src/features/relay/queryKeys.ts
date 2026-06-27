export const relayQueryKeys = {
  bootstrap: ['bootstrap'] as const,
  tokenRefs: ['token-refs'] as const,
  runs: (conversationId: number) => ['runs', conversationId] as const,
  runDetail: (runId: number) => ['run', runId] as const,
}
