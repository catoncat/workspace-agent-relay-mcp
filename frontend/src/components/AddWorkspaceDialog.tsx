import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { ArrowUp, Folder, FolderPlus, Home, Loader2, RefreshCw } from 'lucide-react'
import { browseWorkspaceDirectories } from '@/api/client'
import type { WorkspaceDirectoryBrowseResult } from '@/api/types'
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
import { cn } from '@/lib/utils'

export type AddWorkspaceInput = {
  name?: string
  workingDirectory: string
}

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (input: AddWorkspaceInput) => void | Promise<unknown>
  pending?: boolean
}

export function AddWorkspaceDialog({ open, onOpenChange, onSubmit, pending = false }: Props) {
  const [name, setName] = useState('')
  const [workingDirectory, setWorkingDirectory] = useState('')
  const [browseResult, setBrowseResult] = useState<WorkspaceDirectoryBrowseResult | null>(null)
  const [browseError, setBrowseError] = useState<string | null>(null)
  const [browsing, setBrowsing] = useState(false)

  const loadDirectory = useCallback(async (path?: string | null) => {
    setBrowsing(true)
    setBrowseError(null)
    try {
      const result = await browseWorkspaceDirectories(path)
      setBrowseResult(result)
      setWorkingDirectory(result.path)
    } catch (error) {
      setBrowseResult(null)
      setBrowseError(toErrorMessage(error))
    } finally {
      setBrowsing(false)
    }
  }, [])

  useEffect(() => {
    if (!open) {
      setName('')
      setWorkingDirectory('')
      setBrowseResult(null)
      setBrowseError(null)
      setBrowsing(false)
      return
    }
    void loadDirectory(null)
  }, [loadDirectory, open])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const directory = workingDirectory.trim()
    if (!directory || pending) return
    try {
      await onSubmit({
        name: name.trim() || undefined,
        workingDirectory: directory,
      })
      onOpenChange(false)
    } catch {
      // mutation hooks surface errors to the user
    }
  }

  const parentPath = browseResult?.parent ?? null
  const homePath = browseResult?.home ?? null
  const canSubmit = Boolean(workingDirectory.trim()) && !pending

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !pending && onOpenChange(nextOpen)}>
      <DialogContent className="max-h-[calc(100svh-2rem)] gap-0 overflow-hidden p-0 sm:max-w-2xl">
        <DialogHeader className="border-b px-4 py-3">
          <DialogTitle>Add directory</DialogTitle>
          <DialogDescription>
            Choose a folder on the relay computer, or paste its absolute path.
          </DialogDescription>
        </DialogHeader>

        <form className="grid min-h-0" onSubmit={handleSubmit}>
          <div className="grid min-h-0 gap-4 p-4">
            <div className="grid gap-2">
              <label className="text-xs font-medium text-muted-foreground" htmlFor="workspace-directory">
                Directory path
              </label>
              <div className="flex min-w-0 gap-2">
                <Input
                  id="workspace-directory"
                  autoFocus
                  value={workingDirectory}
                  disabled={pending}
                  placeholder="/Users/me/work/repo"
                  onChange={(event) => setWorkingDirectory(event.target.value)}
                />
                <Button
                  type="button"
                  variant="outline"
                  disabled={pending || browsing || !workingDirectory.trim()}
                  onClick={() => void loadDirectory(workingDirectory)}
                >
                  <RefreshCw className={cn('size-3.5', browsing && 'animate-spin')} />
                  Browse
                </Button>
              </div>
            </div>

            <div className="min-h-0 overflow-hidden rounded-md border bg-background">
              <div className="flex min-h-10 items-center gap-2 border-b px-2 py-1.5">
                <Folder className="size-4 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                  {browseResult?.path ?? 'Host directories'}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  title="Home"
                  disabled={pending || browsing || !homePath}
                  onClick={() => void loadDirectory(homePath)}
                >
                  <Home className="size-3.5" />
                  <span className="sr-only">Home</span>
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  title="Parent directory"
                  disabled={pending || browsing || !parentPath}
                  onClick={() => void loadDirectory(parentPath)}
                >
                  <ArrowUp className="size-3.5" />
                  <span className="sr-only">Parent directory</span>
                </Button>
              </div>
              <div className="max-h-[min(22rem,42svh)] overflow-y-auto p-1">
                {browsing ? (
                  <div className="flex items-center justify-center gap-2 px-3 py-8 text-sm text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" />
                    Loading directories
                  </div>
                ) : browseError ? (
                  <div className="space-y-1 px-3 py-8 text-center text-sm text-muted-foreground">
                    <div>Directory browser unavailable.</div>
                    <div className="text-xs">{browseError}</div>
                  </div>
                ) : browseResult && browseResult.entries.length > 0 ? (
                  browseResult.entries.map((entry) => (
                    <button
                      key={entry.path}
                      type="button"
                      disabled={pending}
                      className="flex w-full min-w-0 items-center gap-2 rounded-md px-2 py-2 text-left text-sm outline-none hover:bg-muted focus-visible:bg-muted disabled:pointer-events-none disabled:opacity-50"
                      onClick={() => void loadDirectory(entry.path)}
                    >
                      <Folder className="size-4 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 truncate">{entry.name}</span>
                    </button>
                  ))
                ) : (
                  <div className="px-3 py-8 text-center text-sm text-muted-foreground">
                    No subdirectories
                  </div>
                )}
                {browseResult?.truncated ? (
                  <div className="px-3 py-2 text-xs text-muted-foreground">
                    Showing the first 500 directories. Type a deeper path to narrow it.
                  </div>
                ) : null}
              </div>
            </div>

            <div className="grid gap-2">
              <label className="text-xs font-medium text-muted-foreground" htmlFor="workspace-name">
                Name
              </label>
              <Input
                id="workspace-name"
                value={name}
                disabled={pending}
                placeholder="Optional"
                onChange={(event) => setName(event.target.value)}
              />
            </div>
          </div>

          <DialogFooter className="border-t px-4 py-3">
            <Button type="button" variant="outline" disabled={pending} onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {pending ? <Loader2 className="size-3.5 animate-spin" /> : <FolderPlus className="size-3.5" />}
              Add directory
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
