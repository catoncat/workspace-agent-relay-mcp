import { createContext, useContext } from 'react'

export type AuthContextValue = {
  token: string
  setToken: (token: string) => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
