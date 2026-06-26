import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { DebugSheet } from '@/components/DebugSheet'
import { RelaySidebar } from '@/components/RelaySidebar'
import { SettingsSheet } from '@/components/SettingsSheet'
import { ThreadView } from '@/components/ThreadView'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
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
  useRunDetailStream,
  useRunDetails,
  useRuns,
} from '@/features/relay/hooks'
import { useAuth } from '@/providers/AuthProvider'

export function RelayPage() {
  const params = useParams<{ conversationId?: string; runId?: string }>()
  const navigate = useNavigate()
  const { token, setToken } = useAuth()

  const selectedConversationId = parseRouteId(params.conversationId)
  const selectedRunId = parseRouteId(params.runId)

  const [settingsOpen, setSettingsOpen] = useState(false)
  const [debugOpen, setDebugOpen] = useState(false)
  const [newConversationOpen, setNewConversationOpen] = useState(false)

  const bootstrapQuery = useBootstrap()
  const agents = bootstrapQuery.data?.agents ?? []
  const conversations = bootstrapQuery.data?.conversations ?? []

  const runsQuery = useRuns(selectedConversationId)
  const runs = runsQuery.data ?? []
  const { details: runDetails } = useRunDetails(runs)
  useRunDetailStream(selectedRunId)

  const createRunMutation = useCreateRun(selectedConversationId)
  const createConversationMutation = useCreateConversation(agents)

  const selectedConversation = useMemo(
    () => conversations.find((conversation) => conversation.id === selectedConversationId) ?? null,
    [conversations, selectedConversationId],
  )
  const selectedDetail = useMemo(
    () => runDetails.find((detail) => detail.run.id === selectedRunId) ?? null,
    [runDetails, selectedRunId],
  )
  const recentUrl = useMemo(
    () => runDetails.map((detail) => detail.run.conversation_url).find(Boolean) ?? null,
    [runDetails],
  )

  useEffect(() => {
    const firstConversation = conversations[0]
    if (!selectedConversationId && firstConversation) {
      navigate(`/c/${firstConversation.id}`, { replace: true })
    }
  }, [conversations, navigate, selectedConversationId])

  useEffect(() => {
    if (!selectedConversationId || selectedRunId || runDetails.length === 0) return
    const latest = runDetails[runDetails.length - 1]
    navigate(`/c/${selectedConversationId}/r/${latest.run.id}`, { replace: true })
  }, [navigate, runDetails, selectedConversationId, selectedRunId])

  const handleSend = useCallback(
    (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || !selectedConversationId) return
      createRunMutation.mutate(trimmed, {
        onSuccess: (detail) => {
          navigate(`/c/${selectedConversationId}/r/${detail.run.id}`)
        },
      })
    },
    [createRunMutation, navigate, selectedConversationId],
  )

  const handleCreateConversation = useCallback(
    (values: NewConversationValues) => {
      createConversationMutation.mutate(values, {
        onSuccess: (conversation) => {
          setNewConversationOpen(false)
          navigate(`/c/${conversation.id}`)
        },
      })
    },
    [createConversationMutation, navigate],
  )

  return (
    <SidebarProvider>
      <RelaySidebar
        conversations={conversations}
        selectedId={selectedConversationId}
        onSelect={(id) => navigate(`/c/${id}`)}
        onNew={() => setNewConversationOpen(true)}
        onRefresh={() => void bootstrapQuery.refetch()}
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
          <ThreadView details={runDetails} />
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
