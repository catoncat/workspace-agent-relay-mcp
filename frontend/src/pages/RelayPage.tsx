import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { DebugSheet } from '@/components/DebugSheet'
import { RelaySidebar } from '@/components/RelaySidebar'
import { SettingsSheet } from '@/components/SettingsSheet'
import { ThreadView, pickActiveRunDetail } from '@/components/ThreadView'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import type { Agent, Conversation, Run } from '@/api/types'
import {
  NewConversationDialog,
  type NewConversationValues,
} from '@/features/relay/components/NewConversationDialog'
import { ThreadComposer } from '@/features/relay/components/ThreadComposer'
import { ThreadHeader } from '@/features/relay/components/ThreadHeader'
import {
  useBootstrap,
  useCreateConversation,
  useCreateRun,
  useDeleteConversation,
  useRenameConversation,
  useRunDetailStream,
  useRunDetails,
  useRuns,
} from '@/features/relay/hooks'
import { useAuth } from '@/providers/AuthContext'

const EMPTY_AGENTS: Agent[] = []
const EMPTY_CONVERSATIONS: Conversation[] = []
const EMPTY_RUNS: Run[] = []

const SELECTED_AGENT_KEY = 'relaySelectedAgentId'

function loadSelectedAgentId(): number | null {
  const raw = localStorage.getItem(SELECTED_AGENT_KEY)
  if (!raw) return null
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : null
}

function saveSelectedAgentId(id: number): void {
  localStorage.setItem(SELECTED_AGENT_KEY, String(id))
}

export function RelayPage() {
  const params = useParams<{ conversationId?: string; runId?: string }>()
  const navigate = useNavigate()
  const { token, setToken } = useAuth()

  const selectedConversationId = parseRouteId(params.conversationId)
  const selectedRunId = parseRouteId(params.runId)

  const [settingsOpen, setSettingsOpen] = useState(false)
  const [debugOpen, setDebugOpen] = useState(false)
  const [newConversationOpen, setNewConversationOpen] = useState(false)
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(loadSelectedAgentId)

  const bootstrapQuery = useBootstrap()
  const agents = bootstrapQuery.data?.agents ?? EMPTY_AGENTS
  const conversations = bootstrapQuery.data?.conversations ?? EMPTY_CONVERSATIONS

  // Keep selectedAgentId valid: once agents load, fall back to the first one if
  // the stored selection no longer exists (or was never set).
  useEffect(() => {
    if (agents.length === 0) return
    if (agents.some((agent) => agent.id === selectedAgentId)) return
    const next = agents[0].id
    setSelectedAgentId(next)
    saveSelectedAgentId(next)
  }, [agents, selectedAgentId])

  const handleSelectAgent = useCallback((id: number) => {
    setSelectedAgentId(id)
    saveSelectedAgentId(id)
  }, [])

  const filteredConversations = useMemo(
    () =>
      selectedAgentId
        ? conversations.filter((conversation) => conversation.agent_id === selectedAgentId)
        : conversations,
    [conversations, selectedAgentId],
  )

  const runsQuery = useRuns(selectedConversationId)
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
  const createConversationMutation = useCreateConversation()
  const renameConversationMutation = useRenameConversation()
  const deleteConversationMutation = useDeleteConversation()

  const selectedConversation = useMemo(
    () => filteredConversations.find((conversation) => conversation.id === selectedConversationId) ?? null,
    [filteredConversations, selectedConversationId],
  )
  const selectedDetail = useMemo(
    () => runDetails.find((detail) => detail.run.id === selectedRunId) ?? null,
    [runDetails, selectedRunId],
  )
  const activeDetail = useMemo(() => pickActiveRunDetail(runDetails), [runDetails])
  const recentUrl = useMemo(
    () => runDetails.map((detail) => detail.run.conversation_url).find(Boolean) ?? null,
    [runDetails],
  )

  useEffect(() => {
    if (filteredConversations.length === 0) return
    const stillSelected = filteredConversations.some(
      (conversation) => conversation.id === selectedConversationId,
    )
    if (!selectedConversationId || !stillSelected) {
      navigate(`/c/${filteredConversations[0].id}`, { replace: true })
    }
  }, [filteredConversations, navigate, selectedConversationId])

  useEffect(() => {
    if (!selectedConversationId || selectedRunId || runDetails.length === 0) return
    const latest = runDetails[runDetails.length - 1]
    navigate(`/c/${selectedConversationId}/r/${latest.run.id}`, { replace: true })
  }, [navigate, runDetails, selectedConversationId, selectedRunId])

  const handleSend = useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || !selectedConversationId) return
      const detail = await createRunMutation.mutateAsync(trimmed)
      navigate(`/c/${selectedConversationId}/r/${detail.run.id}`)
    },
    [createRunMutation, navigate, selectedConversationId],
  )

  const handleCreateConversation = useCallback(
    (values: NewConversationValues) => {
      if (!selectedAgentId) return
      createConversationMutation.mutate(
        { agentId: selectedAgentId, name: values.name, key: values.key },
        {
          onSuccess: (conversation) => {
            setNewConversationOpen(false)
            navigate(`/c/${conversation.id}`)
          },
        },
      )
    },
    [createConversationMutation, navigate, selectedAgentId],
  )

  const handleDeleteConversation = useCallback(
    async (id: number) => {
      await deleteConversationMutation.mutateAsync(id)
      if (selectedConversationId === id) {
        navigate('/', { replace: true })
      }
    },
    [deleteConversationMutation, navigate, selectedConversationId],
  )

  return (
    <SidebarProvider>
      <RelaySidebar
        agents={agents}
        selectedAgentId={selectedAgentId}
        onSelectAgent={handleSelectAgent}
        conversations={filteredConversations}
        selectedId={selectedConversationId}
        onSelect={(id) => navigate(`/c/${id}`)}
        onNew={() => setNewConversationOpen(true)}
        onRefresh={() => void bootstrapQuery.refetch()}
        onRename={(id, name) => renameConversationMutation.mutateAsync({ id, name })}
        onDelete={handleDeleteConversation}
        loading={bootstrapQuery.isLoading || bootstrapQuery.isFetching}
      />

      <SidebarInset className="flex h-svh min-h-0 flex-col overflow-hidden">
        <ThreadHeader
          selectedConversation={selectedConversation}
          selectedDetail={selectedDetail}
          loading={bootstrapQuery.isLoading}
          recentUrl={recentUrl}
          runCount={runDetails.length}
          onOpenDebug={() => setDebugOpen(true)}
          onOpenSettings={() => setSettingsOpen(true)}
        />

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <ThreadView details={runDetails} loading={threadLoading} onSend={handleSend} activeDetail={activeDetail} />
        </div>

        <ThreadComposer
          conversationKey={selectedConversation?.conversation_key}
          disabled={!selectedConversationId}
          sending={createRunMutation.isPending}
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
      <DebugSheet open={debugOpen} onOpenChange={setDebugOpen} detail={selectedDetail} />
      <NewConversationDialog
        open={newConversationOpen}
        pending={createConversationMutation.isPending}
        onOpenChange={setNewConversationOpen}
        onCreate={handleCreateConversation}
      />
    </SidebarProvider>
  )
}

function parseRouteId(value: string | undefined): number | null {
  if (!value) return null
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}
