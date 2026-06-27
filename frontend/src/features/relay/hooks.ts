import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  createAgent,
  createConversation,
  createRun,
  deleteConversation,
  getRunDetail,
  renameConversation,
  streamRun,
} from '@/api/client'
import type { Agent, Conversation, Run, RunDetail } from '@/api/types'
import {
  bootstrapOptions,
  runDetailOptions,
  runsOptions,
  tokenRefsOptions,
} from '@/lib/queryClient'
import { relayQueryKeys } from '@/features/relay/queryKeys'

export type BootstrapData = {
  agents: Agent[]
  conversations: Conversation[]
}

export type CreateConversationInput = {
  agentId: number
  name: string
  key: string
}

export type CreateAgentInput = {
  name: string
  trigger_url: string
  token_ref: string
}

export function useBootstrap() {
  // Not useSuspenseQuery: a missing/invalid dashboard token yields 401 on first
  // run, and we want the shell to render so the user can open Settings and enter
  // a token. Suspense would throw into the route error boundary instead.
  return useQuery(bootstrapOptions)
}

export function useRuns(conversationId: number | null) {
  return useQuery({
    ...runsOptions(conversationId ?? 0),
    enabled: conversationId !== null,
  })
}

export function useRunDetails(runs: Run[]) {
  const detailQueries = useQueries({
    queries: runs.map((run) => runDetailOptions(run.id)),
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
      const { run, triggerFailed, warning } = await createRun(conversationId, input)
      const detail = await getRunDetail(run.id)
      if (triggerFailed) {
        toast.warning(
          warning
            ? `${warning}. Your message was saved — open the run to review or retry.`
            : 'Your message was saved, but triggering the agent failed. Open the run to review or retry.',
        )
      }
      return detail
    },
    onSuccess: (detail) => {
      queryClient.setQueryData(relayQueryKeys.runDetail(detail.run.id), detail)
      if (conversationId) {
        queryClient.setQueryData<Run[]>(relayQueryKeys.runs(conversationId), (current) => {
          const runs = current ?? []
          if (runs.some((run) => run.id === detail.run.id)) return runs
          return [...runs, detail.run].sort((a, b) => a.id - b.id)
        })
        void queryClient.invalidateQueries({ queryKey: relayQueryKeys.runs(conversationId) })
      }
    },
    onError: (err) => {
      toast.error(toError(err).message)
    },
  })
}

export function useTokenRefs() {
  return useQuery(tokenRefsOptions)
}

export function useCreateAgent() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: CreateAgentInput) => createAgent(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: relayQueryKeys.bootstrap })
      void queryClient.invalidateQueries({ queryKey: relayQueryKeys.tokenRefs })
    },
    onError: (err) => {
      toast.error(toError(err).message)
    },
  })
}

export function useCreateConversation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ agentId, name, key }: CreateConversationInput) => {
      if (!agentId) throw new Error('Select an agent before creating a conversation.')
      return createConversation({ agent_id: agentId, name, conversation_key: key })
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: relayQueryKeys.bootstrap })
    },
    onError: (err) => {
      toast.error(toError(err).message)
    },
  })
}

export function useRenameConversation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => renameConversation(id, name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: relayQueryKeys.bootstrap })
    },
    onError: (err) => {
      toast.error(toError(err).message)
    },
  })
}

export function useDeleteConversation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: number) => deleteConversation(id),
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
  return { run, events: [], artifacts: [], plan: null }
}

function toError(err: unknown): Error {
  return err instanceof Error ? err : new Error(String(err))
}

type SendShortcut = {
  label: string
  matches: (event: { key: string; metaKey: boolean; ctrlKey: boolean }) => boolean
}

export function useSendShortcut(): SendShortcut {
  const isMac =
    typeof navigator !== 'undefined' &&
    /mac|iphone|ipad/i.test(navigator.platform)
  const label = isMac ? 'Cmd+Enter' : 'Ctrl+Enter'
  const matches = (event: { key: string; metaKey: boolean; ctrlKey: boolean }) =>
    event.key === 'Enter' && (event.metaKey || event.ctrlKey)
  return { label, matches }
}
