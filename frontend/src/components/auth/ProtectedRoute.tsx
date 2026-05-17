/**
 * Protected Route Component
 *
 * Wraps routes that require authentication.
 * Redirects to login page if user is not authenticated.
 * All features are available to all authenticated users (open source model).
 */

import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import { useBranding } from '../../contexts/BrandingContext'

interface ProtectedRouteProps {
  children: React.ReactNode
  requireSubscription?: boolean  // kept for backward compatibility, not enforced
  requireTeam?: boolean          // kept for backward compatibility, not enforced
}

export function ProtectedRoute({
  children,
}: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, user } = useAuth()
  const { branding, isLoading: brandingLoading } = useBranding()
  const location = useLocation()

  // Show loading state while checking authentication
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-2 border-gray-300 border-t-orange mx-auto mb-4" />
          <p className="text-gray-600 font-serif">Loading...</p>
        </div>
      </div>
    )
  }

  // Redirect to login if not authenticated
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  // First-run setup wizard: bounce the instance admin to the wizard
  // until they finish it. Skip the redirect if branding hasn't loaded
  // yet (avoids a flash to the wizard during the initial fetch) and
  // if they're already on the wizard route.
  const isInstanceAdmin = !!user?.is_instance_admin
  const onWizard = location.pathname.startsWith('/app/instance-setup')
  if (
    !brandingLoading
    && isInstanceAdmin
    && !branding.setup_completed
    && !onWizard
  ) {
    return <Navigate to="/app/instance-setup" replace />
  }

  return <>{children}</>
}
