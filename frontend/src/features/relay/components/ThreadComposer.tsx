import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
} from '@/components/ai-elements/prompt-input'

type Props = {
  conversationKey?: string
  disabled?: boolean
  sending?: boolean
  onSend: (text: string) => void
}

export function ThreadComposer({ conversationKey, disabled = false, sending = false, onSend }: Props) {
  return (
    <footer className="shrink-0 border-t p-3">
      <div className="mx-auto max-w-3xl">
        <PromptInput
          onSubmit={(message, event) => {
            event.preventDefault()
            onSend(message.text)
          }}
        >
          <PromptInputBody>
            <PromptInputTextarea placeholder="Send a task to the Workspace Agent. Reusing the conversation_key continues the same thread." />
          </PromptInputBody>
          <PromptInputFooter>
            <span className="truncate text-xs text-muted-foreground">
              Cmd+Enter to send - <span className="font-mono">{conversationKey ?? '-'}</span>
            </span>
            <PromptInputSubmit
              status={sending ? 'submitted' : undefined}
              disabled={sending || disabled}
            />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </footer>
  )
}
