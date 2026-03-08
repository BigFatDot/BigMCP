/**
 * Protected Route Component
 *
 * Wraps routes that require authentication.
 * Redirects to login page if user is not authenticated.
 */

import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import { useEdition } from '../../hooks/useAuth'

interface ProtectedRouteProps {
  children: React.ReactNode
  requireSubscription?: boolean
  requireTeam?: boolean
}

export function ProtectedRoute({
  children,
  requireSubscription = false,
  requireTeam = false,
}: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, subscription, deploymentConfig } = useAuth()
  const { isCloudSaaS, isCommunity, editionLoading } = useEdition()
  const location = useLocation()

  // Show loading state while checking authentication or edition
  if (isLoading || editionLoading) {
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

  // Check subscription requirement (Cloud SaaS only - not Enterprise or Community)
  // Use isCloudSaaS from backend /edition/status, not hostname-based detection
  if (requireSubscription && isCloudSaaS) {
    if (!subscription || !subscription.is_active) {
      return <Navigate to="/subscribe" state={{ from: location }} replace />
    }
  }

  // Check Team tier requirement
  if (requireTeam) {
    // Use backend edition API (isCloudSaaS) instead of frontend hostname detection
    // This ensures self-hosted deployments on localhost don't see SaaS paywalls
    if (isCloudSaaS && subscription?.tier !== 'team') {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50">
          <div className="max-w-md w-full p-8 bg-white rounded-lg shadow-sm border border-gray-200 text-center">
            <div className="w-16 h-16 bg-orange bg-opacity-10 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg
                className="w-8 h-8 text-orange"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                />
              </svg>
            </div>
            <h2 className="text-2xl font-serif font-bold text-gray-900 mb-2">
              Team Plan Required
            </h2>
            <p className="text-gray-600 mb-6">
              This feature is only available on the Team plan. Upgrade to unlock team
              collaboration, RBAC, OAuth, and shared credentials.
            </p>
            <a
              href="https://bigmcp.cloud/welcome#pricing"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block bg-orange hover:bg-orange-dark text-white font-medium py-2 px-6 rounded-lg transition-colors"
            >
              View Pricing
            </a>
          </div>
        </div>
      )
    }

    // Use backend edition API (isCommunity) instead of frontend hostname detection
    // Community edition users need to upgrade to Enterprise for team features
    if (isCommunity) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50">
          <div className="max-w-md w-full p-8 bg-white rounded-lg shadow-sm border border-gray-200 text-center">
            <div className="w-16 h-16 bg-orange bg-opacity-10 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg
                className="w-8 h-8 text-orange"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                />
              </svg>
            </div>
            <h2 className="text-2xl font-serif font-bold text-gray-900 mb-2">
              Enterprise Edition Required
            </h2>
            <p className="text-gray-600 mb-6">
              Team features are only available in the Enterprise edition. Upgrade to unlock
              multi-user support, RBAC, and team collaboration.
            </p>
            <a
              href="https://bigmcp.cloud/welcome#pricing"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block bg-orange hover:bg-orange-dark text-white font-medium py-2 px-6 rounded-lg transition-colors"
            >
              Learn More
            </a>
          </div>
        </div>
      )
    }
  }

  // Render protected content
  return <>{children}</>
}
