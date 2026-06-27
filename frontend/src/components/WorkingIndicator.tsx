import { cn } from '@/lib/utils'

const ORBIT_NODES = [
  { animation: 'motion-safe:animate-working-node-path-a motion-reduce:animate-none' },
  { animation: 'motion-safe:animate-working-node-path-b motion-reduce:animate-none' },
  { animation: 'motion-safe:animate-working-node-path-c motion-reduce:animate-none' },
] as const

type Props = {
  className?: string
  title?: string
}

export function WorkingIndicator({ className, title = 'Agent working' }: Props) {
  return (
    <span
      className={cn('relative inline-flex size-3 shrink-0 items-center justify-center', className)}
      title={title}
      aria-hidden
    >
      <span className="relative size-2.5">
        {ORBIT_NODES.map((node, index) => (
          <span
            key={index}
            className={cn(
              'absolute left-1/2 top-1/2 size-[2.5px] -ml-[1.25px] -mt-[1.25px] rounded-[0.5px] bg-current',
              node.animation,
            )}
          />
        ))}
      </span>
    </span>
  )
}
