import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from 'react'
import { ApiError, setUnauthorizedHandler } from '../api/client'
import { authApi } from '../api/misc'
import type { Me, RoleCode } from '../types'
import { applyAccent, applyDisplay, clearAccent } from './useTheme'

interface AuthValue {
  user: Me | null
  loading: boolean
  login: (email: string, password: string, remember?: boolean) => Promise<void>
  logout: () => Promise<void>
  hasRole: (...roles: RoleCode[]) => boolean
  refresh: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

/** Forget everything cached for the previous user. The 'me' query stays so its subscribers see the change. */
function dropOtherQueries(client: QueryClient) {
  client.removeQueries({ predicate: (query) => query.queryKey[0] !== 'me' })
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      try {
        return await authApi.me()
      } catch (error) {
        if (error instanceof ApiError && error.status === 403) return null
        throw error
      }
    },
    staleTime: 5 * 60_000,
    retry: false,
  })
  const user = data ?? null

  useEffect(() => {
    if (isLoading) return // keep the cached colours until the account has loaded
    if (user) {
      applyAccent(user.theme ?? '')
      applyDisplay(user.preferences.density, user.preferences.motion)
    } else {
      clearAccent()
    }
  }, [isLoading, user])

  useEffect(() => {
    // Any API call that reports an expired session drops the user back to sign-in.
    setUnauthorizedHandler(() => client.setQueryData(['me'], null))
  }, [client])

  const login = useCallback(
    async (email: string, password: string, remember = false) => {
      const me = await authApi.login(email, password, remember)
      dropOtherQueries(client)
      client.setQueryData(['me'], me)
    },
    [client],
  )

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } finally {
      dropOtherQueries(client)
      client.setQueryData(['me'], null)
    }
  }, [client])

  const value = useMemo<AuthValue>(
    () => ({
      user,
      loading: isLoading,
      login,
      logout,
      hasRole: (...roles) => !!user && roles.some((role) => user.roles.includes(role)),
      refresh: () => void client.invalidateQueries({ queryKey: ['me'] }),
    }),
    [user, isLoading, login, logout, client],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}

/** The signed-in user; only call beneath a route that requires authentication. */
export function useUser(): Me {
  const { user } = useAuth()
  if (!user) throw new Error('No signed-in user')
  return user
}
