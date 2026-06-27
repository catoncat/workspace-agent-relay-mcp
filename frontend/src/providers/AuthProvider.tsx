import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { getAuthToken, setAuthToken } from '@/api/client'
import { AuthContext } from '@/providers/AuthContext'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState(() => getAuthToken())

  useEffect(() => {
    setAuthToken(token)
  }, [token])

  const value = useMemo(() => ({ token, setToken }), [token])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
