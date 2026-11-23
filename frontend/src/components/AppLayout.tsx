import { useState } from 'react'
import { Link, Outlet } from 'react-router-dom'
import { describeError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { BellMark } from './BellMark'

export function AppLayout() {
  const { logout } = useAuth()
  const [loggingOut, setLoggingOut] = useState(false)
  const [logoutError, setLogoutError] = useState<string | null>(null)

  const handleLogout = async () => {
    setLoggingOut(true)
    setLogoutError(null)
    try {
      // 성공하면 인증 상태가 초기화되고 ProtectedRoute가 /login 으로 보낸다.
      await logout()
    } catch (error) {
      setLogoutError(describeError(error, '로그아웃하지 못했습니다. 다시 시도하세요.'))
      setLoggingOut(false)
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-inner">
          <Link to="/events" className="brand">
            <BellMark />
            <span>Smart Doorbell</span>
          </Link>
          <div className="topbar-actions">
            {logoutError && (
              <span className="topbar-error" role="alert">
                {logoutError}
              </span>
            )}
            <button
              type="button"
              className="button button-on-door"
              onClick={handleLogout}
              disabled={loggingOut}
            >
              {loggingOut ? '로그아웃 중...' : '로그아웃'}
            </button>
          </div>
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
    </div>
  )
}
