export const relayQueryKeys = {
  bootstrap: ['bootstrap'] as const,
  runs: (conversationId: number) => ['runs', conversationId] as const,
  runDetail: (runId: number) => ['run', runId] as const,
}
