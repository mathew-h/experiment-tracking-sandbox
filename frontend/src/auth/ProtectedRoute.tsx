import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './AuthContext'
import { PageSpinner } from '@/components/ui'

interface ProtectedRouteProps {
  children: React.ReactNode
}

/** Route guard that redirects unauthenticated users to /login. */
export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { user, loading, configured } = useAuth()
  const location = useLocation()

  // Firebase not configured — let the app render anyway (dev mode)
  if (!configured) return <>{children}</>

  if (loading) {
    return (
      <div className="min-h-screen bg-surface-base flex items-center justify-center">
        <PageSpinner />
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <>{children}</>
}
