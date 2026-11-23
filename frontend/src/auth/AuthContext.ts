import { createContext, useContext } from 'react'

export type AuthStatus =
  | 'checking'
  | 'authenticated'
  | 'unauthenticated'
  /** 서버에 연결하지 못해 인증 여부를 알 수 없는 상태 */
  | 'unreachable'

export interface AuthContextValue {
  status: AuthStatus
  /** 비밀번호가 맞으면 true, 틀리면 false. 그 밖의 실패는 ApiError를 던진다. */
  login: (password: string) => Promise<boolean>
  logout: () => Promise<void>
  /** GET /api/v1/auth/check 를 다시 호출한다. */
  recheck: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth는 AuthProvider 안에서만 사용할 수 있습니다.')
  return value
}
