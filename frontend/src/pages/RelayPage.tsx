import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from '@tanstack/react-router'
import { RelaySidebar, type CreateConversationInput } from '@/components/RelaySidebar'
import { SettingsSheet } from '@/components/SettingsSheet'
import { ThreadView } from '@/components/ThreadView'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import type { Agent, Conversation, RelaySettings, Run, Workspace } from '@/api/types'
import { ThreadComposer, resolveComposerMode } from '@/features/relay/components/ThreadComposer'
import { ThreadHeader } from '@/features/relay/components/ThreadHeader'
import {
  appendQueuedMessage,
  editQueuedMessage,
  mergeQueuedMessages,
  removeQueuedMessage,
  takeQueuedMessage,
  type QueuedComposerMessage,
} from '@/features/relay/queueModel'
import {
  useBootstrap,
  useCreateConversation,
  useCreateRun,
  useDeleteConversation,
  useDismissRun,
  usePinConversation,
  useRenameConversation,
  useRunDetailStream,
  useRunDetails,
  useRuns,
  useSteer,
  useUpdateSettings,
  useWorkingConversationIds,
} from '@/features/relay/hooks'
import type { SendIntent } from '@/features/relay/sendIntent'
import { isConversationWorking, RUN_TERMINAL_STATUSES } from '@/lib/runStatus'
import { useAuth } from '@/providers/AuthContext'
import { nanoid } from 'nanoid'

const EMPTY_AGENTS: Agent[] = []
const EMPTY_CONVERSATIONS: Conversation[] = []
const EMPTY_RUNS: Run[] = []
const EMPTY_WORKSPACES: Workspace[] = []
const DEFAULT_SETTINGS: RelaySettings = {
  current_agent_id: null,
  current_workspace_id: null,
}

export function RelayPage() {
  const params = useParams({ strict: false })
  const navigate = useNavigate()
  const { token, setToken } = useAuth()

  const selectedConversationId = parseRouteId(params.conversationId)
  const selectedRunId = parseRouteId(params.runId)

  const [settingsOpen, setSettingsOpen] = useState(false)
  const [queuedMessages, setQueuedMessages] = useState<QueuedComposerMessage[]>([])
  const [flushQueuedWhenIdle, setFlushQueuedWhenIdle] = useState(false)
  const queuedMessagesRef = useRef<QueuedComposerMessage[]>(queuedMessages)

  const bootstrapQuery = useBootstrap()
  const agents = bootstrapQuery.data?.agents ?? EMPTY_AGENTS
  const settings = bootstrapQuery.data?.settings ?? DEFAULT_SETTINGS
  const workspaces = bootstrapQuery.data?.workspaces ?? EMPTY_WORKSPACES
  const conversations = bootstrapQuery.data?.conversations ?? EMPTY_CONVERSATIONS
  const currentWorkspaceId = settings.current_workspace_id ?? null

  const visibleConversations = useMemo(
    () =>
      conversations.filter(
        (conversation) => (conversation.workspace_id ?? null) === currentWorkspaceId,
      ),
    [conversations, currentWorkspaceId],
  )
  const selectedConversation = useMemo(
    () => visibleConversations.find((conversation) => conversation.id === selectedConversationId) ?? null,
    [selectedConversationId, visibleConversations],
  )
  const activeConversationId = selectedConversation?.id ?? null

  const runsQuery = useRuns(activeConversationId)
  const runs = runsQuery.data ?? EMPTY_RUNS
  const { details: runDetails, isLoading: runDetailsLoading } = useRunDetails(runs)
  useRunDetailStream(selectedRunId)
  const threadLoading = Boolean(
    activeConversationId &&
      (runsQuery.isPending ||
        runsQuery.isPlaceholderData ||
        (runsQuery.isFetching && runs.length === 0) ||
        (runDetailsLoading && runDetails.length === 0)),
  )

  const createRunMutation = useCreateRun(activeConversationId)
  const steerMutation = useSteer(activeConversationId)
  const dismissRunMutation = useDismissRun(activeConversationId)
  const createConversationMutation = useCreateConversation()
  const renameConversationMutation = useRenameConversation()
  const deleteConversationMutation = useDeleteConversation()
  const pinConversationMutation = usePinConversation()
  const updateSettingsMutation = useUpdateSettings()
  const recentUrl = useMemo(
    () => runDetails.map((detail) => detail.run.conversation_url).find(Boolean) ?? null,
    [runDetails],
  )
  const selectedRun = selectedRunId
    ? runDetails.find((detail) => detail.run.id === selectedRunId)?.run
    : null
  const latestActiveRun = useMemo(() => {
    for (let index = runDetails.length - 1; index >= 0; index -= 1) {
      const run = runDetails[index]?.run
      if (run && !RUN_TERMINAL_STATUSES.has(run.status)) return run
    }
    return null
  }, [runDetails])
  const steerTargetRun = selectedRun && !RUN_TERMINAL_STATUSES.has(selectedRun.status)
    ? selectedRun
    : latestActiveRun
  const steerTargetStatus = steerTargetRun?.status
  const sending = createRunMutation.isPending || steerMutation.isPending
  const composerMode = resolveComposerMode(steerTargetStatus, sending)
  const agentWorking = isConversationWorking(steerTargetStatus)

  useEffect(() => {
    queuedMessagesRef.current = queuedMessages
  }, [queuedMessages])

  useEffect(() => {
    if (queuedMessages.length === 0 && flushQueuedWhenIdle) {
      setFlushQueuedWhenIdle(false)
    }
  }, [flushQueuedWhenIdle, queuedMessages.length])

  const conversationIds = useMemo(() => visibleConversations.map((c) => c.id), [visibleConversations])
  const workingConversationIds = useWorkingConversationIds(
    conversationIds,
    activeConversationId,
    steerTargetStatus,
    sending,
  )

  useEffect(() => {
    if (visibleConversations.length === 0) {
      if (selectedConversationId && !bootstrapQuery.isFetching) {
        navigate({ to: '/', replace: true })
      }
      return
    }
    if (!selectedConversationId) {
      navigate({ to: '/c/$conversationId', params: { conversationId: String(visibleConversations[0].id) }, replace: true })
      return
    }
    const stillSelected = visibleConversations.some(
      (conversation) => conversation.id === selectedConversationId,
    )
    if (!stillSelected && !bootstrapQuery.isFetching) {
      navigate({ to: '/c/$conversationId', params: { conversationId: String(visibleConversations[0].id) }, replace: true })
    }
  }, [bootstrapQuery.isFetching, navigate, selectedConversationId, visibleConversations])

  useEffect(() => {
    if (!activeConversationId || selectedRunId || runDetails.length === 0) return
    const latest = runDetails[runDetails.length - 1]
    navigate({ to: '/c/$conversationId/r/$runId', params: { conversationId: String(activeConversationId), runId: String(latest.run.id) }, replace: true })
  }, [activeConversationId, navigate, runDetails, selectedRunId])

  const handleSend = useCallback(
    async (text: string, intent: SendIntent = 'queue') => {
      const trimmed = text.trim()
      if (!trimmed || !activeConversationId) return
      // Cmd/Ctrl+Enter is explicit guidance: reuse the current active run's
      // request_id. Normal Enter while the agent is busy only updates the local
      // FIFO queue; it is not dispatched until the queue is closed/flushed.
      const detail = intent === 'steer' && steerTargetRun
        ? await steerMutation.mutateAsync({ input: trimmed, runId: steerTargetRun?.id })
        : agentWorking
          ? null
          : await createRunMutation.mutateAsync(trimmed)
      if (detail === null) {
        setQueuedMessages((current) => appendQueuedMessage(current, trimmed, nanoid))
        return
      }
      navigate({ to: '/c/$conversationId/r/$runId', params: { conversationId: String(activeConversationId), runId: String(detail.run.id) } })
    },
    [activeConversationId, agentWorking, createRunMutation, navigate, steerMutation, steerTargetRun],
  )

  const handleDismiss = useCallback(async () => {
    if (!steerTargetRun?.id) return
    await dismissRunMutation.mutateAsync(steerTargetRun.id)
  }, [dismissRunMutation, steerTargetRun?.id])

  const handleDeleteQueuedMessage = useCallback((id: string) => {
    setQueuedMessages((current) => removeQueuedMessage(current, id))
  }, [])

  const handleEditQueuedMessage = useCallback((id: string, text: string) => {
    setQueuedMessages((current) => editQueuedMessage(current, id, text))
  }, [])

  const handleSteerQueuedMessage = useCallback(
    async (id: string) => {
      const result = takeQueuedMessage(queuedMessagesRef.current, id)
      if (!result.message) return
      setQueuedMessages(result.queue)
      try {
        await handleSend(result.message.text, 'steer')
      } catch {
        setQueuedMessages((current) => [result.message!, ...current])
      }
    },
    [handleSend],
  )

  const handleCloseQueue = useCallback(() => {
    if (queuedMessagesRef.current.length === 0) return
    setFlushQueuedWhenIdle(true)
  }, [])

  useEffect(() => {
    if (!flushQueuedWhenIdle) return
    if (agentWorking || sending || queuedMessages.length === 0 || !activeConversationId) return

    const messagesToFlush = queuedMessages
    const merged = mergeQueuedMessages(messagesToFlush)
    setQueuedMessages([])
    setFlushQueuedWhenIdle(false)
    if (!merged) return

    void createRunMutation.mutateAsync(merged)
      .then((detail) => {
        navigate({
          to: '/c/$conversationId/r/$runId',
          params: { conversationId: String(activeConversationId), runId: String(detail.run.id) },
        })
      })
      .catch(() => {
        setQueuedMessages((current) => [...messagesToFlush, ...current])
        setFlushQueuedWhenIdle(true)
      })
  }, [
    agentWorking,
    activeConversationId,
    createRunMutation,
    flushQueuedWhenIdle,
    navigate,
    queuedMessages,
    sending,
  ])

  const handleCreateConversation = useCallback(
    async (values: CreateConversationInput) => {
      const conversation = await createConversationMutation.mutateAsync({
        name: values.name,
        key: values.key,
        workspaceId: currentWorkspaceId,
      })
      navigate({
        to: '/c/$conversationId',
        params: { conversationId: String(conversation.id) },
        replace: true,
      })
    },
    [createConversationMutation, currentWorkspaceId, navigate],
  )

  const handleWorkspaceChange = useCallback(
    async (workspaceId: number | null) => {
      await updateSettingsMutation.mutateAsync({ current_workspace_id: workspaceId })
      const target = conversations.find(
        (conversation) => (conversation.workspace_id ?? null) === workspaceId,
      )
      if (target) {
        navigate({
          to: '/c/$conversationId',
          params: { conversationId: String(target.id) },
          replace: true,
        })
        return
      }
      navigate({ to: '/', replace: true })
    },
    [conversations, navigate, updateSettingsMutation],
  )

  const handleDeleteConversation = useCallback(
    async (id: number) => {
      await deleteConversationMutation.mutateAsync(id)
      if (selectedConversationId === id) {
        navigate({ to: '/', replace: true })
      }
    },
    [deleteConversationMutation, navigate, selectedConversationId],
  )

  const handlePinConversation = useCallback(
    async (id: number, pinned: boolean) => {
      await pinConversationMutation.mutateAsync({ id, pinned })
    },
    [pinConversationMutation],
  )

  return (
    <SidebarProvider>
      <RelaySidebar
        workspaces={workspaces}
        currentWorkspaceId={currentWorkspaceId}
        conversations={visibleConversations}
        selectedId={selectedConversationId}
        onWorkspaceChange={handleWorkspaceChange}
        onSelect={(id) => navigate({ to: '/c/$conversationId', params: { conversationId: String(id) } })}
        onCreate={handleCreateConversation}
        creating={createConversationMutation.isPending}
        onRename={(id, name) => renameConversationMutation.mutateAsync({ id, name })}
        onDelete={handleDeleteConversation}
        onPin={handlePinConversation}
        onOpenSettings={() => setSettingsOpen(true)}
        onManageWorkspaces={() => setSettingsOpen(true)}
        loading={bootstrapQuery.isLoading || bootstrapQuery.isFetching}
        workingConversationIds={workingConversationIds}
      />

      <SidebarInset className="flex h-svh min-h-0 flex-col overflow-hidden">
        <ThreadHeader
          selectedConversation={selectedConversation}
          loading={bootstrapQuery.isLoading}
          recentUrl={recentUrl}
          runCount={runDetails.length}
        />

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <ThreadView details={runDetails} loading={threadLoading} onSend={handleSend} />
        </div>

        <ThreadComposer
          conversationKey={selectedConversation?.conversation_key}
          disabled={!activeConversationId}
          dismissing={dismissRunMutation.isPending}
          mode={composerMode}
          canSteer={Boolean(steerTargetRun)}
          queuedMessages={queuedMessages}
          queueFlushPending={flushQueuedWhenIdle}
          onDismiss={handleDismiss}
          onSend={handleSend}
          onQueuedMessageDelete={handleDeleteQueuedMessage}
          onQueuedMessageEdit={handleEditQueuedMessage}
          onQueuedMessageSteer={handleSteerQueuedMessage}
          onCloseQueue={handleCloseQueue}
        />
      </SidebarInset>

      <SettingsSheet
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        token={token}
        onTokenChange={setToken}
        agents={agents}
        settings={settings}
        workspaces={workspaces}
      />
    </SidebarProvider>
  )
}

function parseRouteId(value: string | undefined): number | null {
  if (!value) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}
