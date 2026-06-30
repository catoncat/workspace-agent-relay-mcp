import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from '@tanstack/react-router'
import { toast } from 'sonner'
import { AddWorkspaceDialog, type AddWorkspaceInput } from '@/components/AddWorkspaceDialog'
import { RelaySidebar } from '@/components/RelaySidebar'
import { SettingsSheet } from '@/components/SettingsSheet'
import { ThreadView } from '@/components/ThreadView'
import { WorkspaceCommandMenu } from '@/components/WorkspaceCommandMenu'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import { browseRunFiles, browseWorkspaceFiles } from '@/api/client'
import type {
  Agent,
  Conversation,
  LocalContext,
  RelaySettings,
  Run,
  Workspace,
  WorkspaceFileBrowseResult,
} from '@/api/types'
import { ThreadComposer, resolveComposerMode } from '@/features/relay/components/ThreadComposer'
import { ThreadHeader } from '@/features/relay/components/ThreadHeader'
import {
  planComposerSend,
  planQueueFlush,
  restoreFailedFlush,
} from '@/features/relay/composerController'
import {
  appendQueuedMessage,
  editQueuedMessage,
  getQueuedMessagesForConversation,
  removeQueuedMessage,
  takeQueuedMessage,
  updateQueuedMessagesForConversation,
  type QueuedMessageBuckets,
} from '@/features/relay/queueModel'
import {
  addOptimisticMessage,
  getOptimisticMessagesForConversation,
  removeOptimisticMessage,
  type OptimisticMessageBuckets,
} from '@/features/relay/optimisticMessageModel'
import {
  useBootstrap,
  useCreateConversation,
  useCreateRun,
  useCreateWorkspace,
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
import { buildConversationKey, defaultConversationName } from '@/lib/conversationKey'
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
  const location = useLocation()
  const navigate = useNavigate()
  const { token, setToken } = useAuth()

  const routeConversationId = parseRouteId(params.conversationId)
  const routeRunId = parseRouteId(params.runId)

  const [settingsOpen, setSettingsOpen] = useState(false)
  const [workspaceSwitcherOpen, setWorkspaceSwitcherOpen] = useState(false)
  const [addWorkspaceOpen, setAddWorkspaceOpen] = useState(false)
  const [queuedMessagesByConversation, setQueuedMessagesByConversation] = useState<QueuedMessageBuckets>({})
  const [optimisticMessagesByConversation, setOptimisticMessagesByConversation] = useState<OptimisticMessageBuckets>({})
  const [flushQueuedConversationId, setFlushQueuedConversationId] = useState<number | null>(null)
  const [draftActive, setDraftActive] = useState(location.pathname === '/')
  const [draftFocusToken, setDraftFocusToken] = useState(0)
  const queuedMessagesByConversationRef = useRef<QueuedMessageBuckets>(queuedMessagesByConversation)
  const dispatchingConversationIdsRef = useRef<Set<number>>(new Set())

  const selectedConversationId = draftActive || location.pathname === '/' ? null : routeConversationId
  const selectedRunId = draftActive || location.pathname === '/' ? null : routeRunId

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
  const queuedMessages = useMemo(
    () => getQueuedMessagesForConversation(queuedMessagesByConversation, activeConversationId),
    [activeConversationId, queuedMessagesByConversation],
  )
  const optimisticMessages = useMemo(
    () => getOptimisticMessagesForConversation(optimisticMessagesByConversation, activeConversationId),
    [activeConversationId, optimisticMessagesByConversation],
  )
  const queueFlushPending = flushQueuedConversationId === activeConversationId

  const runsQuery = useRuns(activeConversationId)
  const runs = activeConversationId ? (runsQuery.data ?? EMPTY_RUNS) : EMPTY_RUNS
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
  const createWorkspaceMutation = useCreateWorkspace()
  const updateSettingsMutation = useUpdateSettings()
  const addingWorkspace = createWorkspaceMutation.isPending
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
  const sending = createConversationMutation.isPending || createRunMutation.isPending || steerMutation.isPending
  const composerMode = resolveComposerMode(steerTargetStatus, sending)
  const agentWorking = isConversationWorking(steerTargetStatus)

  useEffect(() => {
    queuedMessagesByConversationRef.current = queuedMessagesByConversation
  }, [queuedMessagesByConversation])

  useEffect(() => {
    if (location.pathname !== '/' && routeConversationId) {
      setDraftActive(false)
    }
  }, [location.pathname, routeConversationId])

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 'k') return
      event.preventDefault()
      setWorkspaceSwitcherOpen(true)
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  useEffect(() => {
    if (flushQueuedConversationId === null) return
    if (getQueuedMessagesForConversation(queuedMessagesByConversation, flushQueuedConversationId).length === 0) {
      setFlushQueuedConversationId(null)
    }
  }, [flushQueuedConversationId, queuedMessagesByConversation])

  useEffect(() => {
    if (!activeConversationId) return
    if (agentWorking || sending) return
    dispatchingConversationIdsRef.current.delete(activeConversationId)
  }, [activeConversationId, agentWorking, sending])

  const conversationIds = useMemo(() => visibleConversations.map((c) => c.id), [visibleConversations])
  const workingConversationIds = useWorkingConversationIds(
    conversationIds,
    activeConversationId,
    steerTargetStatus,
    sending,
  )

  const appendOptimisticMessage = useCallback((conversationId: number, text: string) => {
    const id = nanoid()
    setOptimisticMessagesByConversation((current) =>
      addOptimisticMessage(current, conversationId, text, () => id),
    )
    return id
  }, [])

  const clearOptimisticMessage = useCallback((conversationId: number, id: string) => {
    setOptimisticMessagesByConversation((current) =>
      removeOptimisticMessage(current, conversationId, id),
    )
  }, [])

  const focusDraftComposer = useCallback(() => {
    setDraftFocusToken((value) => value + 1)
  }, [])

  useEffect(() => {
    if (!selectedConversationId) {
      return
    }
    const stillSelected = visibleConversations.some(
      (conversation) => conversation.id === selectedConversationId,
    )
    if (!stillSelected && !bootstrapQuery.isFetching) {
      setDraftActive(true)
      navigate({ to: '/', replace: true })
      focusDraftComposer()
    }
  }, [bootstrapQuery.isFetching, focusDraftComposer, navigate, selectedConversationId, visibleConversations])

  useEffect(() => {
    if (!activeConversationId || selectedRunId || runDetails.length === 0) return
    const latest = runDetails[runDetails.length - 1]
    navigate({ to: '/c/$conversationId/r/$runId', params: { conversationId: String(activeConversationId), runId: String(latest.run.id) }, replace: true })
  }, [activeConversationId, navigate, runDetails, selectedRunId])

  const handleSend = useCallback(
    async (text: string, intent: SendIntent = 'queue', localContext?: LocalContext) => {
      const trimmed = text.trim()
      if (!trimmed) return

      const conversationId = activeConversationId
      if (!conversationId) {
        const fallbackName = defaultConversationName()
        const conversation = await createConversationMutation.mutateAsync({
          name: fallbackName,
          key: buildConversationKey(fallbackName),
          workspaceId: currentWorkspaceId,
        })
        const createdConversationId = conversation.id
        setDraftActive(false)
        navigate({
          to: '/c/$conversationId',
          params: { conversationId: String(createdConversationId) },
          replace: true,
        })
        const optimisticMessageId = appendOptimisticMessage(createdConversationId, trimmed)
        dispatchingConversationIdsRef.current.add(createdConversationId)
        try {
          const detail = await createRunMutation.mutateAsync({
            input: trimmed,
            conversationId: createdConversationId,
            localContext,
          })
          clearOptimisticMessage(createdConversationId, optimisticMessageId)
          navigate({
            to: '/c/$conversationId/r/$runId',
            params: {
              conversationId: String(createdConversationId),
              runId: String(detail.run.id),
            },
            replace: true,
          })
        } catch (error) {
          clearOptimisticMessage(createdConversationId, optimisticMessageId)
          dispatchingConversationIdsRef.current.delete(createdConversationId)
          navigate({
            to: '/c/$conversationId',
            params: { conversationId: String(createdConversationId) },
            replace: true,
          })
          throw error
        }
        return
      }

      const plan = planComposerSend({
        text: trimmed,
        intent,
        conversationId,
        agentWorking,
        sending,
        localDispatchPending: dispatchingConversationIdsRef.current.has(conversationId),
        steerTargetRunId: steerTargetRun?.id,
        localContext,
      })

      if (plan.action === 'ignore') return
      if (plan.action === 'queue') {
        setQueuedMessagesByConversation((current) =>
          updateQueuedMessagesForConversation(current, plan.conversationId, (queue) =>
            appendQueuedMessage(queue, plan.text, nanoid, plan.localContext),
          ),
        )
        return
      }

      const optimisticMessageId = appendOptimisticMessage(plan.conversationId, plan.text)
      let detail: Awaited<ReturnType<typeof createRunMutation.mutateAsync>>
      try {
        detail = plan.action === 'steer'
          ? await steerMutation.mutateAsync({
              input: plan.text,
              localContext: plan.localContext,
              runId: plan.runId,
            })
          : await (async () => {
              dispatchingConversationIdsRef.current.add(plan.conversationId)
              try {
                return await createRunMutation.mutateAsync({
                  input: plan.text,
                  conversationId: plan.conversationId,
                  localContext: plan.localContext,
                })
              } catch (error) {
                dispatchingConversationIdsRef.current.delete(plan.conversationId)
                throw error
              }
            })()
      } catch (error) {
        clearOptimisticMessage(plan.conversationId, optimisticMessageId)
        throw error
      }
      clearOptimisticMessage(plan.conversationId, optimisticMessageId)
      navigate({ to: '/c/$conversationId/r/$runId', params: { conversationId: String(plan.conversationId), runId: String(detail.run.id) } })
    },
    [
      activeConversationId,
      agentWorking,
      appendOptimisticMessage,
      clearOptimisticMessage,
      createConversationMutation,
      createRunMutation,
      currentWorkspaceId,
      navigate,
      sending,
      steerMutation,
      steerTargetRun,
    ],
  )

  const handleDismiss = useCallback(async () => {
    if (!steerTargetRun?.id) return
    await dismissRunMutation.mutateAsync(steerTargetRun.id)
  }, [dismissRunMutation, steerTargetRun?.id])

  const handleDeleteQueuedMessage = useCallback((id: string) => {
    if (!activeConversationId) return
    setQueuedMessagesByConversation((current) =>
      updateQueuedMessagesForConversation(current, activeConversationId, (queue) =>
        removeQueuedMessage(queue, id),
      ),
    )
  }, [activeConversationId])

  const handleEditQueuedMessage = useCallback((id: string, text: string) => {
    if (!activeConversationId) return
    setQueuedMessagesByConversation((current) =>
      updateQueuedMessagesForConversation(current, activeConversationId, (queue) =>
        editQueuedMessage(queue, id, text),
      ),
    )
  }, [activeConversationId])

  const handleSteerQueuedMessage = useCallback(
    async (id: string) => {
      const conversationId = activeConversationId
      if (!conversationId) return
      const result = takeQueuedMessage(
        getQueuedMessagesForConversation(queuedMessagesByConversationRef.current, conversationId),
        id,
      )
      if (!result.message) return
      setQueuedMessagesByConversation((current) =>
        updateQueuedMessagesForConversation(current, conversationId, () => result.queue),
      )
      try {
        await handleSend(result.message.text, 'steer', result.message.localContext)
      } catch {
        setQueuedMessagesByConversation((current) =>
          updateQueuedMessagesForConversation(current, conversationId, (queue) => [result.message!, ...queue]),
        )
      }
    },
    [activeConversationId, handleSend],
  )

  const handleCloseQueue = useCallback(() => {
    const conversationId = activeConversationId
    if (!conversationId) return
    if (getQueuedMessagesForConversation(queuedMessagesByConversationRef.current, conversationId).length === 0) return
    setFlushQueuedConversationId(conversationId)
  }, [activeConversationId])

  useEffect(() => {
    if (flushQueuedConversationId === null) return
    if (flushQueuedConversationId !== activeConversationId) return
    const plan = planQueueFlush({
      flushConversationId: flushQueuedConversationId,
      activeConversationId,
      agentWorking,
      sending,
      localDispatchPending: dispatchingConversationIdsRef.current.has(flushQueuedConversationId),
      queuedMessages,
    })

    if (plan.action === 'wait') return
    if (plan.action === 'ignore') {
      setFlushQueuedConversationId(null)
      return
    }

    const conversationId = plan.conversationId
    const messagesToFlush = plan.messages
    setQueuedMessagesByConversation((current) =>
      updateQueuedMessagesForConversation(current, conversationId, () => []),
    )
    setFlushQueuedConversationId(null)

    const optimisticMessageId = appendOptimisticMessage(conversationId, plan.text)
    void createRunMutation.mutateAsync({
      input: plan.text,
      conversationId,
      localContext: plan.localContext,
    })
      .then((detail) => {
        clearOptimisticMessage(conversationId, optimisticMessageId)
        navigate({
          to: '/c/$conversationId/r/$runId',
          params: { conversationId: String(conversationId), runId: String(detail.run.id) },
        })
      })
      .catch(() => {
        clearOptimisticMessage(conversationId, optimisticMessageId)
        setQueuedMessagesByConversation((current) =>
          updateQueuedMessagesForConversation(current, conversationId, (queue) => [
            ...restoreFailedFlush(messagesToFlush, queue),
          ]),
        )
        setFlushQueuedConversationId(conversationId)
      })
  }, [
    agentWorking,
    appendOptimisticMessage,
    activeConversationId,
    clearOptimisticMessage,
    createRunMutation,
    flushQueuedConversationId,
    navigate,
    queuedMessages,
    sending,
  ])

  const browseComposerFiles = useCallback(
    (path?: string | null): Promise<WorkspaceFileBrowseResult> => {
      if (steerTargetRun?.id) return browseRunFiles(steerTargetRun.id, path)
      if (currentWorkspaceId != null) return browseWorkspaceFiles(currentWorkspaceId, path)
      return Promise.reject(new Error('Select a workspace with a working directory before using @file.'))
    },
    [currentWorkspaceId, steerTargetRun?.id],
  )

  const canBrowseFiles = Boolean(steerTargetRun?.id || currentWorkspaceId != null)

  const handleStartDraftConversation = useCallback(() => {
    setDraftActive(true)
    navigate({ to: '/', replace: true })
    focusDraftComposer()
  }, [focusDraftComposer, navigate])

  const handleSelectConversation = useCallback((id: number) => {
    setDraftActive(false)
    navigate({ to: '/c/$conversationId', params: { conversationId: String(id) } })
  }, [navigate])

  const handleWorkspaceChange = useCallback(
    async (workspaceId: number | null) => {
      await updateSettingsMutation.mutateAsync({ current_workspace_id: workspaceId })
      const target = conversations.find(
        (conversation) => (conversation.workspace_id ?? null) === workspaceId,
      )
      if (target) {
        setDraftActive(false)
        navigate({
          to: '/c/$conversationId',
          params: { conversationId: String(target.id) },
          replace: true,
        })
        return
      }
      setDraftActive(true)
      navigate({ to: '/', replace: true })
      focusDraftComposer()
    },
    [conversations, focusDraftComposer, navigate, updateSettingsMutation],
  )

  const handleCreateWorkspaceFromDirectory = useCallback(async (input: AddWorkspaceInput) => {
    const directory = input.workingDirectory.trim()
    if (!directory) return

    const existing = workspaces.find((workspace) => workspace.working_directory === directory)
    if (existing) {
      await handleWorkspaceChange(existing.id)
      toast.success(`Switched to ${existing.name}`)
      return
    }

    const workspace = await createWorkspaceMutation.mutateAsync({
      name: (input.name?.trim() || workspaceNameFromPath(directory)).trim(),
      working_directory: directory,
    })
    await handleWorkspaceChange(workspace.id)
    toast.success(`Directory added: ${workspace.name}`)
  }, [createWorkspaceMutation, handleWorkspaceChange, workspaces])

  const handleAddWorkspace = useCallback(() => {
    setAddWorkspaceOpen(true)
  }, [])

  const handleSubmitWorkspace = useCallback(async (input: AddWorkspaceInput) => {
    try {
      await handleCreateWorkspaceFromDirectory(input)
    } catch {
      // mutation hooks already surface errors to the user
    }
  }, [handleCreateWorkspaceFromDirectory])

  const handleDeleteConversation = useCallback(
    async (id: number) => {
      await deleteConversationMutation.mutateAsync(id)
      if (selectedConversationId === id) {
        setDraftActive(true)
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
        selectedId={activeConversationId}
        onWorkspaceChange={handleWorkspaceChange}
        onSelect={handleSelectConversation}
        onCreate={handleStartDraftConversation}
        creating={createConversationMutation.isPending}
        onRename={(id, name) => renameConversationMutation.mutateAsync({ id, name })}
        onDelete={handleDeleteConversation}
        onPin={handlePinConversation}
        onOpenSettings={() => setSettingsOpen(true)}
        onAddWorkspace={handleAddWorkspace}
        addingWorkspace={addingWorkspace}
        onOpenWorkspaceSwitcher={() => setWorkspaceSwitcherOpen(true)}
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
          <ThreadView
            details={runDetails}
            loading={threadLoading}
            emptyTitle={activeConversationId ? 'No runs yet' : 'New conversation'}
            emptyDescription={
              activeConversationId
                ? 'Send a task below to trigger the Workspace Agent.'
                : 'Send a task below to create this thread.'
            }
            optimisticMessages={optimisticMessages}
            onSend={handleSend}
          />
        </div>

        <ThreadComposer
          conversationKey={selectedConversation?.conversation_key}
          disabled={bootstrapQuery.isLoading}
          dismissing={dismissRunMutation.isPending}
          focusToken={draftFocusToken}
          mode={composerMode}
          canSteer={Boolean(steerTargetRun)}
          queuedMessages={queuedMessages}
          queueFlushPending={queueFlushPending}
          canBrowseFiles={canBrowseFiles}
          onDismiss={handleDismiss}
          onSend={handleSend}
          onBrowseFiles={browseComposerFiles}
          onQueuedMessageDelete={handleDeleteQueuedMessage}
          onQueuedMessageEdit={handleEditQueuedMessage}
          onQueuedMessageSteer={handleSteerQueuedMessage}
          onCloseQueue={handleCloseQueue}
        />
      </SidebarInset>

      <WorkspaceCommandMenu
        open={workspaceSwitcherOpen}
        onOpenChange={setWorkspaceSwitcherOpen}
        workspaces={workspaces}
        currentWorkspaceId={currentWorkspaceId}
        onSelectWorkspace={handleWorkspaceChange}
        onAddWorkspace={handleAddWorkspace}
        addingWorkspace={addingWorkspace}
        switchingWorkspace={updateSettingsMutation.isPending}
      />

      <AddWorkspaceDialog
        open={addWorkspaceOpen}
        onOpenChange={setAddWorkspaceOpen}
        pending={addingWorkspace || updateSettingsMutation.isPending}
        onSubmit={handleSubmitWorkspace}
      />

      <SettingsSheet
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        token={token}
        onTokenChange={setToken}
        agents={agents}
        settings={settings}
      />
    </SidebarProvider>
  )
}

function workspaceNameFromPath(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean)
  return parts[parts.length - 1] ?? path
}

function parseRouteId(value: string | undefined): number | null {
  if (!value) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}
