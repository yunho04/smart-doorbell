import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'
import { describeError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { BellMark } from '../components/BellMark'

export function LoginPage() {
  const { status, login, recheck } = useAuth()
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (status === 'authenticated') {
    return <Navigate to="/events" replace />
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (submitting || password === '') return

    setSubmitting(true)
    setError(null)
    try {
      const ok = await login(password)
      if (!ok) {
        setError('비밀번호가 올바르지 않습니다.')
        setPassword('')
      }
      // 성공하면 status가 바뀌어 위의 Navigate가 /events 로 보낸다.
    } catch (caught) {
      setError(describeError(caught, '접속하지 못했습니다. 잠시 후 다시 시도하세요.'))
    } finally {
      setSubmitting(false)
    }
  }

  const checking = status === 'checking'
  const serverDown = status === 'unreachable' && !error

  return (
    <div className="door">
      <main className="door-panel">
        <div className="door-bell">
          <BellMark size={56} />
        </div>
        <h1 className="door-title">Smart Doorbell</h1>

        <form className="door-form" onSubmit={handleSubmit} noValidate>
          <label htmlFor="password" className="door-label">
            비밀번호를 입력하세요.
          </label>
          <input
            id="password"
            name="password"
            type="password"
            className="door-input"
            autoComplete="current-password"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={submitting}
            aria-invalid={error ? true : undefined}
            aria-describedby={error || serverDown ? 'login-message' : undefined}
          />
          <button
            type="submit"
            className="door-submit"
            disabled={submitting || checking || password === ''}
          >
            {submitting ? '접속 중...' : '접속'}
          </button>

          <p id="login-message" className="door-message" role="alert">
            {error}
            {serverDown && (
              <>
                서버에 연결할 수 없습니다.{' '}
                <button type="button" className="door-retry" onClick={recheck}>
                  다시 확인
                </button>
              </>
            )}
          </p>
        </form>
      </main>
    </div>
  )
}
