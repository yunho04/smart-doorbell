import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import * as authApi from '../api/auth'
import { ApiError, isAbortError, setUnauthorizedHandler } from '../api/client'
import { AuthContext, type AuthContextValue, type AuthStatus } from './AuthContext'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('checking')
  const [checkCount, setCheckCount] = useState(0)

  // 앱 진입 시(그리고 재시도 시) 로그인 상태를 확인한다.
  useEffect(() => {
    const controller = new AbortController()

    authApi
      .checkAuth(controller.signal)
      .then((result) => {
        setStatus(result?.authenticated === true ? 'authenticated' : 'unauthenticated')
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        // 401도 "인증 안 됨"으로 본다. 그 밖의 실패는 서버 문제로 본다.
        const unauthorized = error instanceof ApiError && error.status === 401
        setStatus(unauthorized ? 'unauthenticated' : 'unreachable')
      })

    return () => controller.abort()
  }, [checkCount])

  // 사용 중 세션이 만료되면(401) 인증 상태를 초기화한다.
  useEffect(() => {
    setUnauthorizedHandler(() => setStatus('unauthenticated'))
    return () => setUnauthorizedHandler(null)
  }, [])

  const login = useCallback(async (password: string) => {
    try {
      const result = await authApi.login(password)
      // 본문 없이 200만 오는 경우도 성공으로 본다.
      const ok = result === undefined || result.authenticated === true
      if (ok) setStatus('authenticated')
      return ok
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return false
      throw error
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await authApi.logout()
    } catch (error) {
      // 이미 세션이 없는 경우(401)는 로그아웃된 것으로 본다.
      if (!(error instanceof ApiError && error.status === 401)) throw error
    }
    setStatus('unauthenticated')
  }, [])

  const recheck = useCallback(() => {
    setStatus('checking')
    setCheckCount((count) => count + 1)
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({ status, login, logout, recheck }),
    [status, login, logout, recheck],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
