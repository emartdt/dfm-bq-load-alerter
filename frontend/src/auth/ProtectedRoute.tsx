import { Navigate, Outlet } from 'react-router-dom'

import { useAuth } from './AuthContext'

export function ProtectedRoute() {
  const { user, loading } = useAuth()
  if (loading) return <p className="loading">불러오는 중…</p>
  if (!user) return <Navigate to="/login" replace />
  return <Outlet />
}
