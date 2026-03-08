/**
 * MainLayout - Main application layout with navbar and bottom nav (mobile)
 */

import { Outlet } from 'react-router-dom'
import { Navbar } from './Navbar'
import { BottomNav } from './BottomNav'
import { PendingInvitationsBanner } from './PendingInvitationsBanner'
import { useAuth } from '@/hooks/useAuth'

export function MainLayout() {
  const { isAuthenticated } = useAuth()

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top Navbar */}
      <Navbar />

      {/* Pending Invitations Banner */}
      <div className="pt-16">
        <PendingInvitationsBanner />
      </div>

      {/* Main Content — extra bottom padding on mobile to clear the bottom nav */}
      <main className={isAuthenticated ? 'pb-20 md:pb-0' : ''}>
        <Outlet />
      </main>

      {/* Bottom Navigation — mobile only, authenticated users */}
      {isAuthenticated && <BottomNav />}
    </div>
  )
}
