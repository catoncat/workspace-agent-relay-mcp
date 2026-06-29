import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from '@tanstack/react-router'
import { RelaySidebar, type CreateConversationInput } from '@/components/RelaySidebar'
import { SettingsSheet } from '@/components/SettingsSheet'
import { ThreadView } from '@/components/ThreadView'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import type { Agent, Conversation, Run } from '@/api/types'
import { ThreadComposer, resolveComposerMode } from '@/features/relay/components/ThreadComposer'
import { ThreadHeader } from '@/features/relay/components/ThreadHeader'
import {
  useBootstrap,
  useConversationPresence,
  useCreateConversation,
  useCreateRun,
  useDeleteConversation,
  useDismissRun,
  usePinConversation,
  usePullSyncStatus,
  useRenameConversation,
  useRunDetailStream,
  useRunDetails,
  useRuns,
  useSetInteractionMode,
  useSteer,
  useWorkingConversationIds,
} from '@/features/relay/hooks'
import { shouldSteerLatestRun } from '@/lib/runStatus'
import { useAuth } from '@/providers/AuthContext'

const EMPTY_AGENTS: Agent[] = []
const EMPTY_CONVERSATIONS: Conversation[] = []
const EMPTY_RUNS: Run[] = []

export function RelayPage() {
  const params = useParams({ strict: false })
  const navigate = useNavigate()
  const { token, setToken } = useAuth()

  const selectedConversationId = parseRouteId(params.conversationId)
  const selectedRunId = parseRouteId(params.runId)

  const [settingsOpen, setSettingsOpen] = useState(false)

  const bootstrapQuery = useBootstrap()
  const agents = bootstrapQuery.data?.agents ?? EMPTY_AGENTS
  const conversations = bootstrapQuery.data?.conversations ?? EMPTY_CONVERSATIONS

  const runsQuery = useRuns(selectedConversationId)
  useConversationPresence(selectedConversationId)
  const runs = runsQuery.data ?? EMPTY_RUNS
  const { details: runDetails, isLoading: runDetailsLoading } = useRunDetails(runs)
  useRunDetailStream(selectedRunId)
  const threadLoading = Boolean(
    selectedConversationId &&
      (runsQuery.isPending ||
        runsQuery.isPlaceholderData ||
        (runsQuery.isFetching && runs.length === 0) ||
        (runDetailsLoading && runDetails.length === 0)),
  )

  const createRunMutation = useCreateRun(selectedConversationId)
  const steerMutation = useSteer(selectedConversationId)
  const dismissRunMutation = useDismissRun(selectedConversationId)
  const createConversationMutation = useCreateConversation()
  const renameConversationMutation = useRenameConversation()
  const deleteConversationMutation = useDeleteConversation()
  const pinConversationMutation = usePinConversation()
  const setInteractionModeMutation = useSetInteractionMode()

  const agentNameById = useMemo(
    () => new Map(agents.map((agent) => [agent.id, agent.name])),
    [agents],
  )

  const selectedConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === selectedConversationId) ?? null,
    [conversations, selectedConversationId],
  )
  const selectedAgentName = selectedConversation
    ? agentNameById.get(selectedConversation.agent_id)
    : undefined
  const recentUrl = useMemo(
    () => runDetails.map((detail) => detail.run.conversation_url).find(Boolean) ?? null,
    [runDetails],
  )
  const latestRun = runDetails[runDetails.length - 1]?.run
  const latestRunStatus = latestRun?.status
  const interactionMode = selectedConversation?.interaction_mode ?? 'relay'
  const pullSync = usePullSyncStatus(selectedConversationId, interactionMode, latestRun?.id)
  // Route composer sends: continue the latest run (steer) when it is in-flight
  // OR paused on ask_user (answering resumes the same turn); otherwise start a
  // new turn. steerConversation falls back to createRun on 409, so a race that
  // turns the run terminal between SSE status and send is still safe.
  const shouldSteer = shouldSteerLatestRun(latestRunStatus)
  const sending = createRunMutation.isPending || steerMutation.isPending
  const composerMode = resolveComposerMode(latestRunStatus, sending)

  const conversationIds = useMemo(() => conversations.map((c) => c.id), [conversations])
  const workingConversationIds = useWorkingConversationIds(
    conversationIds,
    selectedConversationId,
    latestRunStatus,
    sending,
  )

  useEffect(() => {
    if (conversations.length === 0) return
    if (!selectedConversationId) {
      navigate({ to: '/c/$conversationId', params: { conversationId: String(conversations[0].id) }, replace: true })
      return
    }
    const stillSelected = conversations.some(
      (conversation) => conversation.id === selectedConversationId,
    )
    if (!stillSelected && !bootstrapQuery.isFetching) {
      navigate({ to: '/c/$conversationId', params: { conversationId: String(conversations[0].id) }, replace: true })
    }
  }, [bootstrapQuery.isFetching, conversations, navigate, selectedConversationId])

  useEffect(() => {
    if (!selectedConversationId || selectedRunId || runDetails.length === 0) return
    const latest = runDetails[runDetails.length - 1]
    navigate({ to: '/c/$conversationId/r/$runId', params: { conversationId: String(selectedConversationId), runId: String(latest.run.id) }, replace: true })
  }, [navigate, runDetails, selectedConversationId, selectedRunId])

  const handleSend = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || !selectedConversationId) return
      // If the latest run is in-flight OR paused on ask_user, append to it
      // (steer): same turn, plan gets updated rather than redone, and an
      // ask_user answer resumes that turn. Otherwise start a new turn.
      // steerConversation falls back to createRun on 409, so this is safe even
      // if the run went terminal between SSE status and send.
      const detail = shouldSteer
        ? await steerMutation.mutateAsync(trimmed)
        : await createRunMutation.mutateAsync(trimmed)
      navigate({ to: '/c/$conversationId/r/$runId', params: { conversationId: String(selectedConversationId), runId: String(detail.run.id) } })
    },
    [shouldSteer, createRunMutation, navigate, selectedConversationId, steerMutation],
  )

  const handleDismiss = useCallback(async () => {
    if (!latestRun?.id) return
    await dismissRunMutation.mutateAsync(latestRun.id)
  }, [dismissRunMutation, latestRun?.id])

  const handleCreateConversation = useCallback(
    async (values: CreateConversationInput) => {
      const conversation = await createConversationMutation.mutateAsync({
        agentId: values.agentId,
        name: values.name,
        key: values.key,
      })
      navigate({
        to: '/c/$conversationId',
        params: { conversationId: String(conversation.id) },
        replace: true,
      })
    },
    [createConversationMutation, navigate],
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
        agents={agents}
        conversations={conversations}
        selectedId={selectedConversationId}
        onSelect={(id) => navigate({ to: '/c/$conversationId', params: { conversationId: String(id) } })}
        onCreate={handleCreateConversation}
        creating={createConversationMutation.isPending}
        onRename={(id, name) => renameConversationMutation.mutateAsync({ id, name })}
        onDelete={handleDeleteConversation}
        onPin={handlePinConversation}
        onOpenSettings={() => setSettingsOpen(true)}
        loading={bootstrapQuery.isLoading || bootstrapQuery.isFetching}
        workingConversationIds={workingConversationIds}
      />

      <SidebarInset className="flex h-svh min-h-0 flex-col overflow-hidden">
        <ThreadHeader
          selectedConversation={selectedConversation}
          selectedAgentName={agents.length > 1 ? selectedAgentName : undefined}
          loading={bootstrapQuery.isLoading}
          recentUrl={recentUrl}
          runCount={runDetails.length}
          interactionMode={interactionMode}
          interactionModePending={setInteractionModeMutation.isPending}
          pullSyncVisible={pullSync.visible}
          pullSyncState={pullSync.state}
          pullSyncIntervalSec={pullSync.intervalActiveSec}
          onPullSyncResume={() => pullSync.resume()}
          pullSyncResumePending={pullSync.resumePending}
          onInteractionModeChange={(mode) => {
            if (!selectedConversationId) return
            setInteractionModeMutation.mutate({ id: selectedConversationId, interaction_mode: mode })
          }}
        />

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <ThreadView details={runDetails} loading={threadLoading} onSend={handleSend} />
        </div>

        <ThreadComposer
          conversationKey={selectedConversation?.conversation_key}
          interactionMode={selectedConversation?.interaction_mode ?? 'relay'}
          disabled={!selectedConversationId}
          dismissing={dismissRunMutation.isPending}
          mode={composerMode}
          onDismiss={handleDismiss}
          onSend={handleSend}
        />
      </SidebarInset>

      <SettingsSheet
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        token={token}
        onTokenChange={setToken}
        agents={agents}
      />
    </SidebarProvider>
  )
}

function parseRouteId(value: string | undefined): number | null {
  if (!value) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}
