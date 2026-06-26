import { useCallback, useState } from 'react'

export function usePersistedBoolean(key: string, defaultValue: boolean) {
  const [value, setValue] = useState(() => {
    const stored = localStorage.getItem(key)
    if (stored === 'true') return true
    if (stored === 'false') return false
    return defaultValue
  })

  const set = useCallback(
    (next: boolean | ((prev: boolean) => boolean)) => {
      setValue((prev) => {
        const resolved = typeof next === 'function' ? next(prev) : next
        localStorage.setItem(key, String(resolved))
        return resolved
      })
    },
    [key],
  )

  const toggle = useCallback(() => set((v) => !v), [set])

  return [value, set, toggle] as const
}
