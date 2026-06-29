import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import type { PullSyncState } from '@/api/types'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type Props = {
  state: PullSyncState
  intervalActiveSec?: number
  onResume?: () => void
  resumePending?: boolean
}

const LABEL: Record<Exclude<PullSyncState, 'idle'>, string> = {
  offline: 'Poller offline',
  syncing: 'Syncing chat',
  live: 'Synced',
  paused: 'Sync paused',
}

export function PullSyncIndicator({
  state,
  intervalActiveSec = 5,
  onResume,
  resumePending = false,
}: Props) {
  const [flashLive, setFlashLive] = useState(false)
  const prevState = useRef<PullSyncState>('idle')

  useEffect(() => {
    if (prevState.current === 'syncing' && state === 'live') {
      setFlashLive(true)
      const timer = window.setTimeout(() => setFlashLive(false), 1800)
      prevState.current = state
      return () => window.clearTimeout(timer)
    }
    prevState.current = state
    return undefined
  }, [state])

  const visible =
    state === 'paused' || state === 'offline' || state === 'syncing' || (state === 'live' && flashLive)
  const displayState: Exclude<PullSyncState, 'idle'> | null =
    state === 'paused' || state === 'offline' || state === 'syncing'
      ? state
      : state === 'live' && flashLive
        ? 'live'
        : null

  return (
    <AnimatePresence initial={false}>
      {visible && displayState ? (
        <motion.div
          key={displayState}
          initial={{ opacity: 0, scale: 0.92, y: 2 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: -2 }}
          transition={{ type: 'spring', duration: 0.32, bounce: 0 }}
          className={cn(
            'flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium tabular-nums',
            displayState === 'offline' && 'border-amber-500/25 bg-amber-500/8 text-amber-700 dark:text-amber-300',
            displayState === 'syncing' && 'border-sky-500/20 bg-sky-500/8 text-sky-700 dark:text-sky-300',
            displayState === 'live' && 'border-emerald-500/20 bg-emerald-500/8 text-emerald-700 dark:text-emerald-300',
            displayState === 'paused' && 'border-border bg-muted/50 text-muted-foreground',
          )}
          title={
            displayState === 'offline'
              ? 'Hermes poller is not running. Start scripts/hermes_poller_cdp.py to sync ChatGPT messages.'
              : displayState === 'syncing'
                ? `Reading ChatGPT conversation (~every ${intervalActiveSec}s)`
                : displayState === 'paused'
                  ? 'Sync paused while chat is up to date. Click Resume if you expect new messages.'
                  : 'Chat messages are up to date'
          }
        >
          <span className="relative flex size-2 shrink-0 items-center justify-center" aria-hidden>
            {displayState === 'syncing' ? (
              <>
                <span className="absolute size-2 rounded-full bg-sky-500/35 animate-pull-sync-ring" />
                <span className="size-1.5 rounded-full bg-sky-500 animate-pull-sync-core" />
              </>
            ) : (
              <span
                className={cn(
                  'size-1.5 rounded-full',
                  displayState === 'offline' && 'bg-amber-500',
                  displayState === 'live' && 'bg-emerald-500',
                  displayState === 'paused' && 'bg-muted-foreground/60',
                )}
              />
            )}
          </span>
          <span className="text-pretty">{LABEL[displayState]}</span>
          {displayState === 'paused' && onResume ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-5 px-1.5 text-[11px] font-medium text-foreground hover:bg-background/60"
              disabled={resumePending}
              onClick={onResume}
            >
              Resume
            </Button>
          ) : null}
        </motion.div>
      ) : null}
    </AnimatePresence>
  )
}
