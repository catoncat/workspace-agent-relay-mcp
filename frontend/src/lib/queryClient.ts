import { QueryClient, keepPreviousData, queryOptions } from '@tanstack/react-query'
import {
  ensureDefaultAgent,
  getSettings,
  getRunDetail,
  listConversations,
  listRuns,
  listTokenRefs,
  listWorkspaces,
} from '@/api/client'
import type { BootstrapData } from '@/features/relay/hooks'
import { relayQueryKeys } from '@/features/relay/queryKeys'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60 * 1000,
      retry: 1,
    },
  },
})

export const bootstrapOptions = queryOptions({
  queryKey: relayQueryKeys.bootstrap,
  queryFn: async (): Promise<BootstrapData> => {
    const [agents, settings, workspaces, conversations] = await Promise.all([
      ensureDefaultAgent(),
      getSettings(),
      listWorkspaces(),
      listConversations(),
    ])
    return { agents, settings, workspaces, conversations }
  },
  staleTime: 5 * 60 * 1000,
  retry: 1,
})

export const runsOptions = (conversationId: number) =>
  queryOptions({
    queryKey: relayQueryKeys.runs(conversationId),
    queryFn: () => listRuns(conversationId),
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  })

export const runDetailOptions = (runId: number) =>
  queryOptions({
    queryKey: relayQueryKeys.runDetail(runId),
    queryFn: () => getRunDetail(runId),
    staleTime: 30_000,
  })

export const tokenRefsOptions = queryOptions({
  queryKey: relayQueryKeys.tokenRefs,
  queryFn: () => listTokenRefs(),
  staleTime: 60 * 1000,
})
