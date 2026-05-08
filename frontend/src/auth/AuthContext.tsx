import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

import { api } from '../api/client'

export type User = { sub: string; email: string | null; name: string | null }

type AuthState = {
  user: User | null
  loading: boolean
  login: () => void
  logout: () => void
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthState | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const resp = await api.get<User>('/auth/me')
      setUser(resp.data)
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const login = useCallback(() => {
    window.location.href = '/auth/login'
  }, [])

  const logout = useCallback(() => {
    const form = document.createElement('form')
    form.method = 'POST'
    form.action = '/auth/logout'
    document.body.appendChild(form)
    form.submit()
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
