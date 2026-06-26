import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputProvider,
  PromptInputSubmit,
  PromptInputTextarea,
} from '@/components/ai-elements/prompt-input'

type Props = {
  conversationKey?: string
  disabled?: boolean
  sending?: boolean
  onSend: (text: string) => void | Promise<void>
}

export function ThreadComposer({ conversationKey, disabled = false, sending = false, onSend }: Props) {
  const shortcutLabel = getSendShortcutLabel()
  const threadState = conversationKey ? 'Thread linked' : 'No thread selected'

  return (
    <PromptInputProvider>
      <footer className="shrink-0 p-3">
        <div className="mx-auto max-w-3xl">
          <PromptInput
            onSubmit={async (message, event) => {
              event.preventDefault()
              const text = message.text.trim()
              if (!text) return
              await onSend(text)
            }}
          >
            <PromptInputBody>
              <PromptInputTextarea
                className="border-0 bg-transparent shadow-none ring-0 focus-visible:ring-0 dark:bg-transparent px-3 py-2.5"
                placeholder="Send a task to the Workspace Agent..."
              />
            </PromptInputBody>
            <PromptInputFooter>
              <span className="truncate text-xs text-muted-foreground">
                <kbd className="rounded border border-border/60 bg-muted/50 px-1.5 py-0.5 font-mono text-[10px]">{shortcutLabel}</kbd>
                <span className="ml-1.5">to send</span>
                <span className="ml-2 text-muted-foreground/80">{threadState}</span>
              </span>
              <PromptInputSubmit
                status={sending ? 'submitted' : undefined}
                disabled={sending || disabled}
              />
            </PromptInputFooter>
          </PromptInput>
        </div>
      </footer>
    </PromptInputProvider>
  )
}

function getSendShortcutLabel(): string {
  if (typeof navigator === 'undefined') return 'Ctrl+Enter'
  const platform = navigator.platform.toLowerCase()
  return platform.includes('mac') || platform.includes('iphone') || platform.includes('ipad')
    ? 'Cmd+Enter'
    : 'Ctrl+Enter'
}
