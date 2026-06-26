import { useEffect, useId, useState } from 'react'
import type { FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'

export type NewConversationValues = {
  name: string
  key: string
}

type Props = {
  open: boolean
  pending?: boolean
  onOpenChange: (open: boolean) => void
  onCreate: (values: NewConversationValues) => void
}

export function NewConversationDialog({
  open,
  pending = false,
  onOpenChange,
  onCreate,
}: Props) {
  const nameId = useId()
  const keyId = useId()
  const [name, setName] = useState('New conversation')
  const [key, setKey] = useState(defaultConversationKey('New conversation'))
  const [keyTouched, setKeyTouched] = useState(false)

  useEffect(() => {
    if (!open) return
    setName('New conversation')
    setKey(defaultConversationKey('New conversation'))
    setKeyTouched(false)
  }, [open])

  useEffect(() => {
    if (!keyTouched) setKey(defaultConversationKey(name))
  }, [keyTouched, name])

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmedName = name.trim()
    const trimmedKey = key.trim()
    if (!trimmedName || !trimmedKey) return
    onCreate({ name: trimmedName, key: trimmedKey })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>New conversation</DialogTitle>
            <DialogDescription>
              Create a reusable conversation key for future runs in this thread.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-2">
            <label htmlFor={nameId} className="text-sm font-medium">
              Name
            </label>
            <Input
              id={nameId}
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoComplete="off"
            />
          </div>

          <div className="grid gap-2">
            <label htmlFor={keyId} className="text-sm font-medium">
              Conversation key
            </label>
            <Input
              id={keyId}
              value={key}
              onChange={(event) => {
                setKeyTouched(true)
                setKey(event.target.value)
              }}
              className="font-mono"
              autoComplete="off"
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending || !name.trim() || !key.trim()}>
              {pending ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function defaultConversationKey(name: string): string {
  const slug =
    name
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ':')
      .replace(/^:|:$/g, '') || 'conversation'
  return `${slug}:${new Date().toISOString().slice(0, 10)}`
}
