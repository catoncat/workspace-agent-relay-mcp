import { cn } from '@/lib/utils'
import { cjk } from '@streamdown/cjk'
import { code as codePlugin } from '@streamdown/code'
import { math } from '@streamdown/math'
import { mermaid } from '@streamdown/mermaid'
import { CheckIcon, CopyIcon } from 'lucide-react'
import {
  isValidElement,
  useState,
  type HTMLAttributes,
  type ReactNode,
} from 'react'
import { Streamdown, type Components, type CustomRendererProps, type ExtraProps } from 'streamdown'

const streamdownPlugins = { cjk, code: codePlugin, math, mermaid }

const threadProseClass = cn(
  'thread-prose text-sm leading-relaxed text-foreground/90 [&>*:first-child]:mt-0 [&>*:last-child]:mb-0',
)

type ThreadProseProps = {
  children: string
  className?: string
}

const threadMarkdownComponents: Components = {
  code: ThreadMarkdownCode,
  ul: ThreadUl,
  ol: ThreadOl,
  li: ThreadLi,
}

export function ThreadProse({ children, className }: ThreadProseProps) {
  return (
    <Streamdown
      mode="static"
      className={cn(threadProseClass, className)}
      plugins={streamdownPlugins}
      components={threadMarkdownComponents}
      lineNumbers={false}
      controls={{ code: { copy: false, download: false } }}
    >
      {children}
    </Streamdown>
  )
}

type MarkdownCodeProps = HTMLAttributes<HTMLElement> & ExtraProps & {
  'data-block'?: boolean
}

/** Intercept every fenced code block — including `text` / `txt` which Shiki
 * does not list — so Streamdown never renders its default CodeBlock chrome. */
function ThreadMarkdownCode({ className, children, ...props }: MarkdownCodeProps) {
  const isBlock = 'data-block' in props && props['data-block'] !== false

  if (!isBlock) {
    return (
      <code
        className={cn(
          'rounded bg-muted/50 px-1 py-0.5 font-mono text-[0.85em] text-foreground/90',
          className,
        )}
        {...props}
      >
        {children}
      </code>
    )
  }

  const code = extractText(children).replace(/\n+$/, '')

  return <CompactCode code={code} language="" isIncomplete={false} />
}

function ThreadUl(props: HTMLAttributes<HTMLElement> & ExtraProps) {
  const { className, children, ...rest } = props
  return (
    <ul
      className={cn('my-2 list-none space-y-1.5 pl-0', className)}
      data-streamdown="unordered-list"
      {...rest}
    >
      {children}
    </ul>
  )
}

function ThreadOl(props: HTMLAttributes<HTMLElement> & ExtraProps) {
  const { className, children, ...rest } = props
  return (
    <ol
      className={cn('my-2 list-none space-y-1.5 pl-0 [counter-reset:thread-ol]', className)}
      data-streamdown="ordered-list"
      {...rest}
    >
      {children}
    </ol>
  )
}

function ThreadLi(props: HTMLAttributes<HTMLElement> & ExtraProps) {
  const { className, children, ...rest } = props
  return (
    <li
      className={cn(
        'flex gap-2.5 py-0.5 leading-relaxed',
        '[ol_&]:before:mr-0 [ol_&]:before:min-w-[1.1rem] [ol_&]:before:shrink-0 [ol_&]:before:text-right [ol_&]:before:text-muted-foreground/70 [ol_&]:before:content-[counter(thread-ol)\".\"] [ol_&]:before:[counter-increment:thread-ol]',
        className,
      )}
      data-streamdown="list-item"
      {...rest}
    >
      <span
        aria-hidden
        className="mt-[0.55em] size-1 shrink-0 rounded-full bg-muted-foreground/45 [ol_&]:hidden"
      />
      <span className="min-w-0 flex-1 [&>p:first-child]:inline [&>p:only-child]:m-0 [&_code]:break-all [&_code]:whitespace-normal">
        {children}
      </span>
    </li>
  )
}

function CompactCode({ code }: CustomRendererProps) {
  const trimmed = code.replace(/\n+$/, '')
  const isSingleLine = !trimmed.includes('\n')

  if (isSingleLine) {
    return <CopyableRow text={trimmed} />
  }

  return (
    <div className="group/code relative my-2">
      <CopyButton
        text={trimmed}
        className="absolute right-1.5 top-1.5 opacity-0 transition-opacity group-hover/code:opacity-100"
      />
      <pre className="max-h-96 overflow-x-auto overflow-y-auto rounded-md bg-muted/40 p-3 text-xs leading-relaxed">
        <code className="font-mono text-foreground/85">{trimmed}</code>
      </pre>
    </div>
  )
}

function CopyableRow({ text }: { text: string }) {
  return (
    <div className="group/code my-1 flex items-center gap-2 rounded-md bg-muted/40 px-3 py-1.5">
      <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap font-mono text-xs text-foreground/85">
        {text}
      </code>
      <CopyButton text={text} className="shrink-0 text-muted-foreground/70 transition-colors hover:text-foreground" />
    </div>
  )
}

function CopyButton({ text, className }: { text: string; className?: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1200)
    } catch {
      setCopied(false)
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={copied ? 'Copied' : 'Copy'}
      className={cn('inline-flex size-6 items-center justify-center', className)}
    >
      {copied ? (
        <CheckIcon className="size-3.5 text-green-600 dark:text-green-500" />
      ) : (
        <CopyIcon className="size-3.5" />
      )}
    </button>
  )
}

function extractText(node: ReactNode): string {
  if (typeof node === 'string') return node
  if (typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(extractText).join('')
  if (isValidElement<{ children?: ReactNode }>(node)) {
    return extractText(node.props.children)
  }
  return ''
}
