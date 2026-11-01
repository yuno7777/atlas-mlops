import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { api, clearSession, getToken, readStoredUser, setSession } from '../api/client'
import type { TokenResponse, User } from '../api/types'

interface AuthContextValue {
  user: User | null
  ready: boolean
  login: (email: string, password: string) => Promise<void>
  register: (input: {
    email: string
    password: string
    full_name: string
    workspace_name?: string
  }) => Promise<void>
  logout: () => void
  updateUser: (user: User) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => readStoredUser<User>())
  const [ready, setReady] = useState(false)

  const logout = useCallback(() => {
    clearSession()
    setUser(null)
  }, [])

  useEffect(() => {
    let cancelled = false
    const token = getToken()
    if (!token) {
      setReady(true)
      return
    }
    api
      .get<User>('/auth/me')
      .then((current) => {
        if (cancelled) return
        setUser(current)
        localStorage.setItem('atlas.user', JSON.stringify(current))
      })
      .catch(() => {
        if (!cancelled) logout()
      })
      .finally(() => {
        if (!cancelled) setReady(true)
      })
    return () => {
      cancelled = true
    }
  }, [logout])

  useEffect(() => {
    const handler = () => logout()
    window.addEventListener('atlas:unauthorized', handler)
    return () => window.removeEventListener('atlas:unauthorized', handler)
  }, [logout])

  const applySession = useCallback((response: TokenResponse) => {
    setSession(response.access_token, response.user)
    setUser(response.user)
  }, [])

  const login = useCallback(
    async (email: string, password: string) => {
      const response = await api.post<TokenResponse>('/auth/login', { email, password })
      applySession(response)
    },
    [applySession],
  )

  const register = useCallback(
    async (input: {
      email: string
      password: string
      full_name: string
      workspace_name?: string
    }) => {
      const response = await api.post<TokenResponse>('/auth/register', input)
      applySession(response)
    },
    [applySession],
  )

  const updateUser = useCallback((next: User) => {
    setUser(next)
    localStorage.setItem('atlas.user', JSON.stringify(next))
  }, [])

  const value = useMemo(
    () => ({ user, ready, login, register, logout, updateUser }),
    [user, ready, login, register, logout, updateUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
