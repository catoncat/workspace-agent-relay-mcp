import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQueries, useQuery, useQueryClient, type Query } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  createAgent,
  createConversation,
  createRun,
  dismissRun,
  deleteAgent,
  deleteConversation,
  getRunDetail,
  getPullSyncStatus,
  postConversationPresence,
  renameAgent,
  renameConversation,
  setConversationPinned,
  setConversationInteractionMode,
  setConversationPollingPaused,
  steerConversation,
  streamRun,
  updateAgent,
} from '@/api/client'
import type { Agent, Conversation, InteractionMode, PullSyncState, Run, RunDetail } from '@/api/types'
import {
  bootstrapOptions,
  runDetailOptions,
  runsOptions,
  tokenRefsOptions,
} from '@/lib/queryClient'
import { relayQueryKeys } from '@/features/relay/queryKeys'
import { isConversationWorking, latestRunStatusFromRuns } from '@/lib/runStatus'

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
  access_token: string
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

/** Tell the relay which conversation the operator is viewing (drives Hermes poller). */
export function useConversationPresence(conversationId: number | null) {
  useEffect(() => {
    if (!conversationId) return
    let cancelled = false
    const ping = () => {
      if (cancelled || document.visibilityState === 'hidden') return
      void postConversationPresence(conversationId).catch(() => {})
    }
    ping()
    const intervalId = window.setInterval(ping, 10_000)
    const onVisibility = () => {
      if (document.visibilityState === 'visible') ping()
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      cancelled = true
      window.clearInterval(intervalId)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [conversationId])
}

/** Pull-mode sync pill: poller online/offline + catch-up state for the active run. */
export function usePullSyncStatus(
  conversationId: number | null,
  _interactionMode: InteractionMode,
  latestRunId: number | undefined,
) {
  const queryClient = useQueryClient()
  const autoPauseTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const query = useQuery({
    queryKey: relayQueryKeys.pullSync(conversationId ?? 0),
    queryFn: () => getPullSyncStatus(conversationId!),
    enabled: conversationId !== null,
    refetchInterval: (q) => {
      const state = q.state.data?.state
      if (state === 'syncing' || state === 'offline') return 3_000
      if (state === 'paused') return 10_000
      return 8_000
    },
  })

  const resumeMutation = useMutation({
    mutationFn: () => setConversationPollingPaused(conversationId!, false),
    onSuccess: () => {
      if (!conversationId) return
      void queryClient.invalidateQueries({ queryKey: relayQueryKeys.pullSync(conversationId) })
    },
    onError: () => {
      toast.error('Could not resume sync')
    },
  })

  useEffect(() => {
    if (!conversationId) return
    void queryClient.invalidateQueries({ queryKey: relayQueryKeys.pullSync(conversationId) })
  }, [conversationId, latestRunId, queryClient])

  useEffect(() => {
    if (autoPauseTimer.current) {
      window.clearTimeout(autoPauseTimer.current)
      autoPauseTimer.current = null
    }
    if (!conversationId) return undefined
    const data = query.data
    if (!data?.visible || !data || data.polling_paused || data.state !== 'live' || data.needs_sync) return undefined
    autoPauseTimer.current = window.setTimeout(() => {
      void setConversationPollingPaused(conversationId, true).then(() => {
        void queryClient.invalidateQueries({ queryKey: relayQueryKeys.pullSync(conversationId) })
      })
    }, 6_000)
    return () => {
      if (autoPauseTimer.current) {
        window.clearTimeout(autoPauseTimer.current)
        autoPauseTimer.current = null
      }
    }
  }, [
    conversationId,
    query.data?.visible,
    query.data?.state,
    query.data?.needs_sync,
    query.data?.polling_paused,
    queryClient,
  ])

  const visible = query.data?.visible === true
  const state: PullSyncState = !visible ? 'idle' : (query.data?.state ?? 'idle')
  const intervalActiveSec = query.data?.interval_active_sec ?? 5

  return {
    visible,
    state,
    intervalActiveSec,
    isLoading: query.isPending,
    resume: () => resumeMutation.mutate(),
    resumePending: resumeMutation.isPending,
  }
}

/** Poll each conversation's run list; derive sidebar "working" from latest run status. */
export function useWorkingConversationIds(
  conversationIds: number[],
  selectedConversationId: number | null,
  selectedLatestStatus: string | undefined,
  sendingRun: boolean,
): ReadonlySet<number> {
  const runListQueries = useQueries({
    queries: conversationIds.map((id) => ({
      ...runsOptions(id),
      refetchInterval: (query: Query<Run[], Error, Run[], ReturnType<typeof relayQueryKeys.runs>>) => {
        const status = latestRunStatusFromRuns(query.state.data)
        return isConversationWorking(status) ? 5_000 : 30_000
      },
    })),
  })

  const runListData = runListQueries.map((query) => query.data)

  return useMemo(() => {
    const working = new Set<number>()
    for (let index = 0; index < conversationIds.length; index += 1) {
      const id = conversationIds[index]!
      if (id === selectedConversationId && sendingRun) {
        working.add(id)
        continue
      }
      const status =
        id === selectedConversationId && selectedLatestStatus !== undefined
          ? selectedLatestStatus
          : latestRunStatusFromRuns(runListData[index])
      if (isConversationWorking(status)) working.add(id)
    }
    return working
  }, [conversationIds, runListData, selectedConversationId, selectedLatestStatus, sendingRun])
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

export function useDismissRun(conversationId: number | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (runId: number) => dismissRun(runId),
    onSuccess: (detail) => {
      queryClient.setQueryData(relayQueryKeys.runDetail(detail.run.id), detail)
      if (conversationId) {
        queryClient.setQueryData<Run[]>(relayQueryKeys.runs(conversationId), (current) => {
          const runs = current ?? []
          return runs.map((run) => (run.id === detail.run.id ? detail.run : run))
        })
        void queryClient.invalidateQueries({ queryKey: relayQueryKeys.runs(conversationId) })
      }
    },
    onError: (err) => {
      toast.error(toError(err).message)
    },
  })
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

export function useSteer(conversationId: number | null) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (input: string) => {
      if (!conversationId) throw new Error('Select a conversation before sending a task.')
      // steerConversation falls back to createRun on 409 (no active run), so
      // this returns a RunDetail either way.
      const { run, triggerFailed, warning } = await steerConversation(conversationId, input)
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
        // Steer reuses an existing run, so it is already in the list; still
        // invalidate so status/trigger fields refresh.
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

export function useUpdateAgent() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; name?: string; access_token?: string }) =>
      updateAgent(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: relayQueryKeys.bootstrap })
    },
    onError: (err) => {
      toast.error(toError(err).message)
    },
  })
}

export function useRenameAgent() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) => renameAgent(id, name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: relayQueryKeys.bootstrap })
    },
    onError: (err) => {
      toast.error(toError(err).message)
    },
  })
}

export function useDeleteAgent() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: number) => deleteAgent(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: relayQueryKeys.bootstrap })
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
    onSuccess: (conversation) => {
      queryClient.setQueryData<BootstrapData>(relayQueryKeys.bootstrap, (current) => {
        if (!current) return current
        const conversations = [
          conversation,
          ...current.conversations.filter((item) => item.id !== conversation.id),
        ]
        return { ...current, conversations }
      })
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

export function usePinConversation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, pinned }: { id: number; pinned: boolean }) =>
      setConversationPinned(id, pinned),
    onMutate: async ({ id, pinned }) => {
      await queryClient.cancelQueries({ queryKey: relayQueryKeys.bootstrap })
      const previous = queryClient.getQueryData<BootstrapData>(relayQueryKeys.bootstrap)
      queryClient.setQueryData<BootstrapData>(relayQueryKeys.bootstrap, (current) => {
        if (!current) return current
        const pinned_at = pinned ? new Date().toISOString() : null
        const conversations = current.conversations
          .map((conversation) =>
            conversation.id === id ? { ...conversation, pinned_at } : conversation,
          )
          .sort((a, b) => {
            const aPinned = a.pinned_at ? 0 : 1
            const bPinned = b.pinned_at ? 0 : 1
            if (aPinned !== bPinned) return aPinned - bPinned
            return 0
          })
        return { ...current, conversations }
      })
      return { previous }
    },
    onSuccess: (_conversation, { pinned }) => {
      toast.success(pinned ? 'Pinned' : 'Unpinned')
      void queryClient.invalidateQueries({ queryKey: relayQueryKeys.bootstrap })
    },
    onError: (err, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(relayQueryKeys.bootstrap, context.previous)
      }
      toast.error(toError(err).message)
    },
  })
}

export function useSetInteractionMode() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, interaction_mode }: { id: number; interaction_mode: InteractionMode }) =>
      setConversationInteractionMode(id, interaction_mode),
    onMutate: async ({ id, interaction_mode }) => {
      await queryClient.cancelQueries({ queryKey: relayQueryKeys.bootstrap })
      const previous = queryClient.getQueryData<BootstrapData>(relayQueryKeys.bootstrap)
      queryClient.setQueryData<BootstrapData>(relayQueryKeys.bootstrap, (current) => {
        if (!current) return current
        return {
          ...current,
          conversations: current.conversations.map((conversation) =>
            conversation.id === id ? { ...conversation, interaction_mode } : conversation,
          ),
        }
      })
      return { previous }
    },
    onSuccess: (_conversation, { interaction_mode }) => {
      toast.success(interaction_mode === 'pull' ? 'Pull mode' : 'Relay mode')
      void queryClient.invalidateQueries({ queryKey: relayQueryKeys.bootstrap })
    },
    onError: (err, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(relayQueryKeys.bootstrap, context.previous)
      }
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
