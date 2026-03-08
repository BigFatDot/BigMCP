/**
 * Navbar - Top navigation bar with BigMCP branding
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  UserCircleIcon,
  ChevronDownIcon,
  ArrowRightOnRectangleIcon,
  Cog6ToothIcon,
  UserIcon,
  CreditCardIcon,
  UsersIcon,
  KeyIcon,
} from '@heroicons/react/24/outline'
import { useAuth, useSubscription, useFeatureAccess, useEdition } from '../../hooks/useAuth'
import { BigMCPLogoWithText } from '../brand/BigMCPLogo'

export function Navbar() {
  const { t } = useTranslation('common')
  const { isAuthenticated, user, logout } = useAuth()
  const { isInTrial, daysUntilTrialEnd } = useSubscription()
  const { features } = useFeatureAccess()
  const { isCloudSaaS, isEnterprise, isCommunity } = useEdition()
  const [showUserMenu, setShowUserMenu] = useState(false)

  return (
    <nav className="fixed top-0 left-0 right-0 z-40 bg-white border-b border-gray-200">
      <div className="container">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link to="/app" className="flex items-center">
            <BigMCPLogoWithText size="sm" textSize="md" />
          </Link>

          {/* Navigation Links */}
          <div className="hidden md:flex items-center gap-6">
            <Link
              to="/app/marketplace"
              className="text-sm font-medium text-gray-700 hover:text-orange transition-colors"
            >
              {t('nav.marketplace')}
            </Link>
            {isAuthenticated && (
              <>
                <Link
                  to="/app/tools"
                  className="text-sm font-medium text-gray-700 hover:text-orange transition-colors"
                >
                  {t('nav.services')}
                </Link>
                <Link
                  to="/app/compositions"
                  className="text-sm font-medium text-gray-700 hover:text-orange transition-colors"
                >
                  {t('nav.compositions')}
                </Link>
              </>
            )}
            <Link
              to="/docs"
              className="text-sm font-medium text-gray-700 hover:text-orange transition-colors"
            >
              {t('nav.documentation')}
            </Link>
          </div>

          {/* Right Actions */}
          <div className="flex items-center gap-3">
            {/* Trial Badge */}
            {isAuthenticated && isInTrial && daysUntilTrialEnd && daysUntilTrialEnd > 0 && (
              <div className="hidden md:flex items-center gap-2 px-3 py-1 bg-blue-50 border border-blue-200 rounded-full">
                <svg className="w-4 h-4 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z"
                    clipRule="evenodd"
                  />
                </svg>
                <span className="text-xs font-medium text-blue-700">
                  {t('trial.daysLeft', { count: daysUntilTrialEnd })}
                </span>
              </div>
            )}

            {/* Documentation link - mobile only (desktop uses the nav links above) */}
            <Link
              to="/docs"
              className="md:hidden text-sm font-medium text-gray-700 hover:text-orange transition-colors px-2"
            >
              {t('nav.documentation')}
            </Link>

            {isAuthenticated ? (
              <>
                {/* User Menu */}
                <div className="relative">
                  <button
                    onClick={() => setShowUserMenu(!showUserMenu)}
                    className="flex items-center gap-2 p-2 hover:bg-gray-100 rounded-lg transition-colors"
                  >
                    <UserCircleIcon className="h-8 w-8 text-gray-600" />
                    <ChevronDownIcon className="hidden md:block h-4 w-4 text-gray-600" />
                  </button>

                  {/* Dropdown Menu */}
                  {showUserMenu && (
                    <>
                      {/* Backdrop */}
                      <div
                        className="fixed inset-0 z-10"
                        onClick={() => setShowUserMenu(false)}
                      />

                      {/* Menu */}
                      <div className="absolute right-0 mt-2 w-64 bg-white rounded-lg shadow-lg border border-gray-200 py-2 z-20">
                        {/* User Info */}
                        <div className="px-4 py-3 border-b border-gray-200">
                          <p className="text-sm font-medium text-gray-900">{user?.full_name}</p>
                          <p className="text-xs text-gray-500 truncate">{user?.email}</p>
                        </div>

                        {/* Menu Items */}
                        <div className="py-2">
                          <Link
                            to="/app/account"
                            className="flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                            onClick={() => setShowUserMenu(false)}
                          >
                            <UserIcon className="h-5 w-5 text-gray-400" />
                            {t('menu.account')}
                          </Link>

                          {/* Subscription menu item - SaaS only */}
                          {isCloudSaaS && (
                            <Link
                              to="/app/subscription"
                              className="flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                              onClick={() => setShowUserMenu(false)}
                            >
                              <CreditCardIcon className="h-5 w-5 text-gray-400" />
                              {t('menu.subscription')}
                            </Link>
                          )}
                          {/* Enterprise/Community: License info is in Account Settings */}

                          <Link
                            to="/app/api-keys"
                            className="flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                            onClick={() => setShowUserMenu(false)}
                          >
                            <KeyIcon className="h-5 w-5 text-gray-400" />
                            {t('menu.apiKeys')}
                          </Link>

                          {!isCommunity && (
                            <Link
                              to="/app/organization"
                              className="flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                              onClick={() => setShowUserMenu(false)}
                            >
                              <UsersIcon className="h-5 w-5 text-gray-400" />
                              {t('menu.team')}
                            </Link>
                          )}

                          <Link
                            to="/app/preferences"
                            className="flex items-center gap-3 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                            onClick={() => setShowUserMenu(false)}
                          >
                            <Cog6ToothIcon className="h-5 w-5 text-gray-400" />
                            {t('menu.preferences')}
                          </Link>
                        </div>

                        {/* Logout */}
                        <div className="border-t border-gray-200 pt-2">
                          <button
                            onClick={() => {
                              logout()
                              setShowUserMenu(false)
                            }}
                            className="flex items-center gap-3 px-4 py-2 text-sm text-red-600 hover:bg-red-50 transition-colors w-full"
                          >
                            <ArrowRightOnRectangleIcon className="h-5 w-5" />
                            {t('menu.signout')}
                          </button>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </>
            ) : (
              <>
                {/* Login / Signup for unauthenticated users */}
                <Link
                  to="/login"
                  className="hidden md:block text-sm font-medium text-gray-700 hover:text-gray-900 transition-colors"
                >
                  {t('nav.signin')}
                </Link>
                <Link
                  to="/signup"
                  className="bg-orange hover:bg-orange-dark text-white font-medium text-sm px-4 py-2 rounded-lg transition-colors"
                >
                  {t('nav.startTrial')}
                </Link>
              </>
            )}

          </div>
        </div>
      </div>
    </nav>
  )
}
