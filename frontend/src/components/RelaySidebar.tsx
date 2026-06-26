import { MessageSquarePlus, RefreshCw } from 'lucide-react'
import type { Conversation } from '@/api/types'
import { Button } from '@/components/ui/button'
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupAction,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from '@/components/ui/sidebar'

type Props = {
  conversations: Conversation[]
  selectedId: number | null
  onSelect: (id: number) => void
  onNew: () => void
  onRefresh: () => void
  loading?: boolean
}

export function RelaySidebar({
  conversations,
  selectedId,
  onSelect,
  onNew,
  onRefresh,
  loading = false,
}: Props) {
  return (
    <Sidebar collapsible="offcanvas">
      <SidebarHeader className="border-b border-sidebar-border">
        <div className="flex items-center gap-2 px-2 py-1">
          <div className="flex size-6 items-center justify-center rounded-md bg-primary text-[10px] font-bold text-primary-foreground">
            AR
          </div>
          <span className="font-semibold tracking-tight">Agent Relay</span>
          <Button
            variant="ghost"
            size="icon-sm"
            className="ml-auto text-muted-foreground"
            title="Refresh conversations"
            onClick={onRefresh}
            disabled={loading}
          >
            <RefreshCw className={loading ? 'animate-spin' : ''} />
          </Button>
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Conversations</SidebarGroupLabel>
          <SidebarGroupAction title="New conversation" onClick={onNew}>
            <MessageSquarePlus />
            <span className="sr-only">New conversation</span>
          </SidebarGroupAction>
          <SidebarGroupContent>
            <SidebarMenu>
              {conversations.length === 0 ? (
                <p className="px-2 py-3 text-xs text-muted-foreground">
                  {loading ? 'Loading…' : 'No conversations yet.'}
                </p>
              ) : (
                conversations.map((item) => (
                  <SidebarMenuItem key={item.id}>
                    <SidebarMenuButton
                      isActive={item.id === selectedId}
                      onClick={() => onSelect(item.id)}
                      tooltip={item.name}
                    >
                      <span className="truncate font-medium">{item.name}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))
              )}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarRail />
    </Sidebar>
  )
}
