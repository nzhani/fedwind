"use client"

// Who is logged in (SITE_NETWORK_PLAN.md §3). The session lives in an httpOnly cookie set by the
// API; this context only keeps the user and the session's CSRF token in memory.

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import {
  getMe,
  login as apiLogin,
  logout as apiLogout,
  registerOperator,
  setCsrfToken,
  type AccountUser,
  type SessionInfo,
} from "@/lib/platform-api"

interface AuthState {
  user: AccountUser | null
  loading: boolean
  isAdmin: boolean
  login: (email: string, password: string) => Promise<AccountUser>
  register: (body: { email: string; password: string; name: string; organization: string }) => Promise<AccountUser>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionInfo | null>(null)
  const [loading, setLoading] = useState(true)

  const apply = useCallback((s: SessionInfo | null) => {
    setSession(s)
    setCsrfToken(s?.csrf_token ?? null)
  }, [])

  const refresh = useCallback(async () => {
    try {
      apply(await getMe())
    } catch {
      apply(null) // API or database down: behave as logged out
    } finally {
      setLoading(false)
    }
  }, [apply])

  useEffect(() => {
    refresh()
  }, [refresh])

  const value = useMemo<AuthState>(
    () => ({
      user: session?.user ?? null,
      loading,
      isAdmin: session?.user.role === "admin",
      login: async (email, password) => {
        const s = await apiLogin(email, password)
        apply(s)
        return s.user
      },
      register: async (body) => {
        const s = await registerOperator(body)
        apply(s)
        return s.user
      },
      logout: async () => {
        try {
          await apiLogout()
        } finally {
          apply(null)
        }
      },
      refresh,
    }),
    [session, loading, apply, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>")
  return ctx
}
