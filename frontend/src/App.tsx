import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/AppLayout'
import { ProtectedRoute } from './components/ProtectedRoute'
import { EventDetailPage } from './pages/EventDetailPage'
import { EventListPage } from './pages/EventListPage'
import { LoginPage } from './pages/LoginPage'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      {/* 인증이 필요한 화면. 인증되지 않으면 /login 으로 보낸다. */}
      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/events" element={<EventListPage />} />
          <Route path="/events/:eventId" element={<EventDetailPage />} />
        </Route>
      </Route>

      {/* "/" 와 알 수 없는 주소는 /events 로 보내고, 인증 여부는 ProtectedRoute가 판단한다. */}
      <Route path="*" element={<Navigate to="/events" replace />} />
    </Routes>
  )
}
