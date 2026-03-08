import { Routes, Route, Navigate } from 'react-router-dom'
import { ToastProvider } from './components/ui'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import { ProtectedRoute } from './components/auth/ProtectedRoute'
import { MainLayout } from './components/layout/MainLayout'
import { MarketplaceBrowser } from './components/marketplace/MarketplaceBrowser'
import { ToolsDashboard } from './components/dashboard/ToolsDashboard'
import { OnboardingWizard } from './components/onboarding/OnboardingWizard'
import { LoginPage } from './pages/auth/LoginPage'
import { SignupPage } from './pages/auth/SignupPage'
import { AcceptInvitationPage } from './pages/auth/AcceptInvitationPage'
import { VerifyEmailPage } from './pages/auth/VerifyEmailPage'
import { VerifyEmailPendingPage } from './pages/auth/VerifyEmailPendingPage'
import { LandingPage } from './pages/LandingPage'
import { CompositionsPage } from './pages/compositions'
import {
  APIKeysPage,
  AccountPage,
  TeamPage,
  SubscriptionPage,
  PreferencesPage,
} from './pages/settings'
import { DocsLayout, DocPage } from './pages/docs'
import { NotFoundPage } from './pages/NotFoundPage'
import { TermsPage } from './pages/TermsPage'
import { PrivacyPage } from './pages/PrivacyPage'
import { ReloadPrompt } from './components/pwa/ReloadPrompt'

function App() {
  return (
    <AuthProvider>
      {/* Toast Notifications */}
      <ToastProvider />

      {/* Routes */}
      <Routes>
        {/* Public Routes - Authentication */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/oauth/callback" element={<OAuthCallback />} />
        <Route path="/invitations/:token/accept" element={<AcceptInvitationPage />} />
        {/* Email Verification */}
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/verify-email-pending" element={<VerifyEmailPendingPage />} />

        {/* Onboarding (for new users after signup) */}
        <Route
          path="/onboarding"
          element={
            <ProtectedRoute>
              <OnboardingWizard />
            </ProtectedRoute>
          }
        />

        {/* Landing Page - Standalone (outside MainLayout), for Cloud mode visitors */}
        <Route path="/welcome" element={<LandingPage />} />

        {/* Legal Pages - Public */}
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />

        {/* Documentation - Public, SEO-optimized */}
        <Route path="/docs" element={<DocsLayout />}>
          <Route index element={<Navigate to="/docs/getting-started/introduction" replace />} />
          <Route path=":section/:slug" element={<DocPage />} />
        </Route>

        {/* Root Route - Redirects based on deployment mode and auth state */}
        <Route path="/" element={<RootRoute />} />

        {/* Main App with Layout */}
        <Route path="/app" element={<MainLayout />}>
          {/* Marketplace - accessible to all authenticated or self-hosted users */}
          <Route index element={<MarketplaceBrowser />} />
          <Route path="marketplace" element={<MarketplaceBrowser />} />

          {/* Protected Routes - require authentication */}
          <Route
            path="tools"
            element={
              <ProtectedRoute>
                <ToolsDashboard />
              </ProtectedRoute>
            }
          />
          {/* Redirect old my-servers route to tools */}
          <Route path="my-servers" element={<Navigate to="/app/tools" replace />} />
          <Route
            path="compositions"
            element={
              <ProtectedRoute>
                <CompositionsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="account"
            element={
              <ProtectedRoute>
                <AccountPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="subscription"
            element={
              <ProtectedRoute>
                <SubscriptionPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="api-keys"
            element={
              <ProtectedRoute>
                <APIKeysPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="organization"
            element={
              <ProtectedRoute requireTeam>
                <TeamPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="preferences"
            element={
              <ProtectedRoute>
                <PreferencesPage />
              </ProtectedRoute>
            }
          />
        </Route>

        {/* 404 Catch-all */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>

      {/* PWA Update Prompt */}
      <ReloadPrompt />
    </AuthProvider>
  )
}

/**
 * OAuth Callback Handler
 * Handles the OAuth redirect and sends the result to the parent window
 */
function OAuthCallback() {
  const params = new URLSearchParams(window.location.search)
  const code = params.get('code')
  const state = params.get('state')
  const error = params.get('error')

  // Send message to parent window
  if (window.opener) {
    if (error) {
      window.opener.postMessage(
        {
          type: 'oauth_error',
          error: error,
        },
        window.location.origin
      )
    } else if (code && state) {
      window.opener.postMessage(
        {
          type: 'oauth_success',
          code,
          state,
        },
        window.location.origin
      )
    }
    window.close()
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-2 border-gray-300 border-t-orange mx-auto mb-4" />
        <p className="text-gray-600 font-serif">
          {error ? 'Authorization failed. You can close this window.' : 'Completing authorization...'}
        </p>
      </div>
    </div>
  )
}

/**
 * Root Route Component
 *
 * Redirects based on deployment mode and authentication state:
 * - Cloud mode + not authenticated → /welcome (Landing Page)
 * - Cloud mode + authenticated → /app (Marketplace)
 * - Self-hosted (any) → /app (Marketplace)
 */
function RootRoute() {
  const { isAuthenticated, deploymentConfig, isLoading } = useAuth()

  // Show loading while auth state is being determined
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-gray-300 border-t-orange" />
      </div>
    )
  }

  // Cloud mode: show landing page for non-authenticated visitors
  if (deploymentConfig.is_cloud && !isAuthenticated) {
    return <Navigate to="/welcome" replace />
  }

  // Self-hosted or authenticated: go directly to services (my servers)
  return <Navigate to="/app/tools" replace />
}

export default App
