import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function ProtectedRoute() {
  const { status, recheck } = useAuth()

  if (status === 'checking') {
    return (
      <div className="fullscreen-state">
        <p className="state-text" role="status">
          로그인 상태를 확인하는 중...
        </p>
      </div>
    )
  }

  if (status === 'unreachable') {
    return (
      <div className="fullscreen-state">
        <div className="state-block" role="alert">
          <p className="state-title">서버에 연결할 수 없습니다.</p>
          <p className="state-text">Backend 서버가 켜져 있는지 확인한 뒤 다시 시도하세요.</p>
          <button type="button" className="button" onClick={recheck}>
            다시 시도
          </button>
        </div>
      </div>
    )
  }

  if (status === 'unauthenticated') {
    return <Navigate to="/login" replace />
  }

  return <Outlet />
}
