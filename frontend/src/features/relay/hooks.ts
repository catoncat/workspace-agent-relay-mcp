import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  createConversation,
  createRun,
  ensureDefaultAgent,
  ensureDefaultConversation,
  getRunDetail,
  listRuns,
  streamRun,
} from '@/api/client'
import type { Agent, Conversation, Run, RunDetail } from '@/api/types'
import { relayQueryKeys } from '@/features/relay/queryKeys'

export type BootstrapData = {
  agents: Agent[]
  conversations: Conversation[]
}

export type CreateConversationInput = {
  name: string
  key: string
}

const EMPTY_RUNS: Run[] = []

export function useBootstrap() {
  return useQuery({
    queryKey: relayQueryKeys.bootstrap,
    queryFn: async (): Promise<BootstrapData> => {
      const agents = await ensureDefaultAgent()
      const firstAgent = agents[0]
      const conversations = firstAgent ? await ensureDefaultConversation(firstAgent.id) : []
      return { agents, conversations }
    },
    staleTime: 5 * 60 * 1000,
    retry: 1,
  })
}

export function useRuns(conversationId: number | null) {
  return useQuery({
    queryKey: relayQueryKeys.runs(conversationId ?? 0),
    queryFn: () => listRuns(conversationId!),
    enabled: conversationId !== null,
    placeholderData: (previous) => previous ?? EMPTY_RUNS,
    refetchInterval: 30_000,
  })
}

export function useRunDetails(runs: Run[]) {
  const detailQueries = useQueries({
    queries: runs.map((run) => ({
      queryKey: relayQueryKeys.runDetail(run.id),
      queryFn: () => getRunDetail(run.id),
      staleTime: 30_000,
    })),
  })

  const details = useMemo(
    () =>
      detailQueries
        .map((query, index) => query.data ?? emptyRunDetail(runs[index]))
        .sort((a, b) => a.run.id - b.run.id),
    [detailQueries, runs],
  )

  return {
    details,
    isLoading: detailQueries.some((query) => query.isLoading),
    isFetching: detailQueries.some((query) => query.isFetching),
  }
}

export function useRunDetailStream(runId: number | null) {
  const queryClient = useQueryClient()
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    if (!runId) return
    const controller = new AbortController()
    setError(null)

    void streamRun(
      runId,
      (detail) => {
        queryClient.setQueryData(relayQueryKeys.runDetail(detail.run.id), detail)
      },
      controller.signal,
    ).catch((err: unknown) => {
      if (controller.signal.aborted) return
      const streamError = toError(err)
      setError(streamError)
      toast.error(streamError.message)
    })

    return () => controller.abort()
  }, [queryClient, runId])

  return { error }
}

export function useCreateRun(conversationId: number | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (input: string) => {
      if (!conversationId) throw new Error('Select a conversation before sending a task.')
      const run = await createRun(conversationId, input)
      return getRunDetail(run.id)
    },
    onSuccess: (detail) => {
      queryClient.setQueryData(relayQueryKeys.runDetail(detail.run.id), detail)
      if (conversationId) {
        void queryClient.invalidateQueries({ queryKey: relayQueryKeys.runs(conversationId) })
      }
    },
    onError: (err) => {
      toast.error(toError(err).message)
    },
  })
}

export function useCreateConversation(agents: Agent[]) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ name, key }: CreateConversationInput) => {
      const agent = agents[0]
      if (!agent) throw new Error('No agents available.')
      return createConversation({ agent_id: agent.id, name, conversation_key: key })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: relayQueryKeys.bootstrap })
    },
    onError: (err) => {
      toast.error(toError(err).message)
    },
  })
}

function emptyRunDetail(run: Run | undefined): RunDetail {
  if (!run) throw new Error('Run detail query is missing a run placeholder.')
  return { run, events: [], artifacts: [] }
}

function toError(err: unknown): Error {
  return err instanceof Error ? err : new Error(String(err))
}
