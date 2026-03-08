/**
 * BottomNav - Mobile bottom navigation bar
 *
 * Shown only on mobile (hidden md+). Fixed at bottom with safe-area support.
 * 3 tabs: Marketplace | Services | Compositions
 */

import { NavLink, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Squares2X2Icon,
  CircleStackIcon,
  PuzzlePieceIcon,
} from '@heroicons/react/24/outline'
import {
  Squares2X2Icon as Squares2X2IconSolid,
  CircleStackIcon as CircleStackIconSolid,
  PuzzlePieceIcon as PuzzlePieceIconSolid,
} from '@heroicons/react/24/solid'
import { useAuth } from '@/hooks/useAuth'

interface NavItem {
  to: string
  labelKey: string
  Icon: React.ComponentType<{ className?: string }>
  IconActive: React.ComponentType<{ className?: string }>
  requiresAuth?: boolean
}

const NAV_ITEMS: NavItem[] = [
  {
    to: '/app/marketplace',
    labelKey: 'nav.marketplace',
    Icon: Squares2X2Icon,
    IconActive: Squares2X2IconSolid,
  },
  {
    to: '/app/tools',
    labelKey: 'nav.services',
    Icon: CircleStackIcon,
    IconActive: CircleStackIconSolid,
    requiresAuth: true,
  },
  {
    to: '/app/compositions',
    labelKey: 'nav.compositions',
    Icon: PuzzlePieceIcon,
    IconActive: PuzzlePieceIconSolid,
    requiresAuth: true,
  },
]

export function BottomNav() {
  const { t } = useTranslation('common')
  const { isAuthenticated } = useAuth()
  const location = useLocation()

  const visibleItems = NAV_ITEMS.filter(
    item => !item.requiresAuth || isAuthenticated
  )

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-40 bg-white border-t border-gray-200 md:hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <div className="flex items-stretch h-16">
        {visibleItems.map(({ to, labelKey, Icon, IconActive }) => {
          const isActive =
            location.pathname === to ||
            (to === '/app/marketplace' && location.pathname === '/app')

          return (
            <NavLink
              key={to}
              to={to}
              className="flex-1 flex flex-col items-center justify-center gap-1 transition-colors"
            >
              {isActive ? (
                <>
                  <IconActive className="h-6 w-6 text-orange" />
                  <span className="text-[10px] font-semibold text-orange leading-none">
                    {t(labelKey)}
                  </span>
                </>
              ) : (
                <>
                  <Icon className="h-6 w-6 text-gray-400" />
                  <span className="text-[10px] font-medium text-gray-400 leading-none">
                    {t(labelKey)}
                  </span>
                </>
              )}
            </NavLink>
          )
        })}
      </div>
    </nav>
  )
}
