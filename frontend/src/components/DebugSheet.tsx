import type { RunDetail } from '@/api/types'
import { RunInspector } from '@/components/RunInspector'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  detail: RunDetail | null
}

export function DebugSheet({ open, onOpenChange, detail }: Props) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-md">
        <SheetHeader className="border-b px-4 py-4">
          <SheetTitle>Trigger trace</SheetTitle>
          <SheetDescription>
            Relay accepts your task (HTTP 202), then the Workspace Agent reports back via MCP
            callbacks. This panel shows trigger metadata, artifacts, and raw JSON — not a live chat
            stream.
          </SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-hidden">
          <RunInspector detail={detail} />
        </div>
      </SheetContent>
    </Sheet>
  )
}
