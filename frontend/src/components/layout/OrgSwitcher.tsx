/**
 * OrgSwitcher — pill autonome dans la navbar exposant l'organisation
 * courante + un dropdown pour basculer entre les memberships du user.
 *
 * Rules (cf. Sprint 3.B contract) :
 * - `!isAuthenticated`              → render null
 * - `memberships.length === 0`      → render null (cas dégénéré post-self-heal)
 * - `memberships.length === 1`      → libellé non interactif (juste un badge)
 * - `memberships.length > 1`        → pill cliquable + dropdown avec rôles
 *
 * a11y :
 * - aria-haspopup="menu" + aria-expanded sur le button
 * - role="menu" sur le dropdown + role="menuitem" sur chaque entrée
 * - Escape ferme, click outside (backdrop) ferme
 *
 * Single source of truth : useOrganization() (factorisé Sprint 3.B).
 */

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDownIcon, CheckIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { useAuth, useOrganization } from '../../hooks/useAuth'

interface UserOrganizationDTO {
  id: string
  name: string
  slug: string
  organization_type: string
  role: string
  joined_at: string | null
}

export function OrgSwitcher() {
  const { t } = useTranslation('common')
  const { isAuthenticated } = useAuth()
  const {
    organizationId,
    organizationName,
    memberships,
    switchOrganization,
  } = useOrganization()

  const [isOpen, setIsOpen] = useState(false)
  const [isSwitching, setIsSwitching] = useState(false)
  const [orgs, setOrgs] = useState<UserOrganizationDTO[]>([])
  const [loadingOrgs, setLoadingOrgs] = useState(false)

  // Fetch organizations (with names + roles) only when authenticated and
  // when the user actually has more than one membership — single-org case
  // doesn't need the round-trip, the badge uses organizationName directly.
  useEffect(() => {
    if (!isAuthenticated || memberships.length <= 1) {
      return
    }
    let cancelled = false
    const fetchOrgs = async () => {
      setLoadingOrgs(true)
      try {
        const token = localStorage.getItem('bigmcp_access_token')
        const response = await fetch('/api/v1/auth/organizations', {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        if (!response.ok) {
          return
        }
        const data = await response.json()
        if (!cancelled) {
          setOrgs(data.organizations || [])
        }
      } catch {
        // Silent: dropdown will still render with the active org name.
      } finally {
        if (!cancelled) {
          setLoadingOrgs(false)
        }
      }
    }
    void fetchOrgs()
    return () => {
      cancelled = true
    }
  }, [isAuthenticated, memberships.length])

  // Escape ferme le dropdown
  useEffect(() => {
    if (!isOpen) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [isOpen])

  if (!isAuthenticated) {
    return null
  }

  if (memberships.length === 0) {
    return null
  }

  // Single-org case → badge non interactif (cf. décision UX 3.B)
  if (memberships.length === 1) {
    if (!organizationName) {
      return null
    }
    return (
      <span
        className="hidden md:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-gray-200 bg-gray-50 text-xs font-medium text-gray-700"
        title={t('orgSwitcher.current')}
        aria-label={`${t('orgSwitcher.current')}: ${organizationName}`}
      >
        {organizationName}
      </span>
    )
  }

  const handleSwitch = async (orgId: string) => {
    if (orgId === organizationId || isSwitching) {
      setIsOpen(false)
      return
    }
    setIsSwitching(true)
    try {
      await switchOrganization(orgId)
      // No success toast — page reload est l'effet visible (contrat Sprint 2).
    } catch (err) {
      setIsSwitching(false)
      setIsOpen(false)
      const fallback = t('orgSwitcher.errorFallback')
      toast.error(err instanceof Error && err.message ? err.message : fallback)
    }
  }

  const buttonLabel = isSwitching
    ? t('orgSwitcher.switching')
    : organizationName || t('orgSwitcher.current')

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => !isSwitching && setIsOpen((v) => !v)}
        disabled={isSwitching}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label={t('orgSwitcher.current')}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-gray-200 bg-gray-50 hover:bg-gray-100 text-xs font-medium text-gray-900 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
      >
        <span className="max-w-[14rem] truncate">{buttonLabel}</span>
        <ChevronDownIcon className="h-3.5 w-3.5 text-gray-500" aria-hidden="true" />
      </button>

      {isOpen && (
        <>
          {/* Backdrop pour click-outside (pattern hérité du user-menu Navbar) */}
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
            aria-hidden="true"
          />

          <div
            role="menu"
            aria-label={t('orgSwitcher.current')}
            className="absolute right-0 mt-2 w-72 max-h-80 overflow-y-auto bg-white rounded-lg shadow-lg border border-gray-200 py-2 z-20"
          >
            <div className="px-3 pb-1.5 text-[10px] uppercase tracking-wide text-gray-400">
              {t('orgSwitcher.current')}
            </div>

            {loadingOrgs && orgs.length === 0 && (
              <div className="px-3 py-2 text-sm text-gray-500">
                {t('status.loading')}
              </div>
            )}

            {orgs.length > 0 && orgs.map((org) => {
              const isActive = org.id === organizationId
              return (
                <button
                  key={org.id}
                  type="button"
                  role="menuitem"
                  onClick={() => handleSwitch(org.id)}
                  disabled={isSwitching}
                  className="w-full flex items-center justify-between gap-3 px-3 py-2 text-sm text-left text-gray-700 hover:bg-gray-50 transition-colors disabled:cursor-not-allowed"
                >
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-gray-900 truncate">
                      {org.name}
                    </div>
                    <div className="text-xs text-gray-500 truncate">
                      {org.role}
                    </div>
                  </div>
                  {isActive && (
                    <CheckIcon
                      className="h-4 w-4 text-gray-500 flex-shrink-0"
                      aria-label={t('orgSwitcher.current')}
                    />
                  )}
                  {!isActive && !isSwitching && (
                    <span className="text-[10px] uppercase tracking-wide text-gray-400 flex-shrink-0">
                      {t('orgSwitcher.switchTo')}
                    </span>
                  )}
                </button>
              )
            })}

            {/* Fallback : si /auth/organizations échoue, on liste au moins
                les memberships connus (org_id + role) pour ne pas bloquer
                le switch. */}
            {!loadingOrgs && orgs.length === 0 &&
              memberships.map((m) => {
                const isActive = m.organization_id === organizationId
                const label = isActive && organizationName
                  ? organizationName
                  : m.organization_id
                return (
                  <button
                    key={m.id}
                    type="button"
                    role="menuitem"
                    onClick={() => handleSwitch(m.organization_id)}
                    disabled={isSwitching}
                    className="w-full flex items-center justify-between gap-3 px-3 py-2 text-sm text-left text-gray-700 hover:bg-gray-50 transition-colors disabled:cursor-not-allowed"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="font-medium text-gray-900 truncate">
                        {label}
                      </div>
                      <div className="text-xs text-gray-500 truncate">
                        {m.role}
                      </div>
                    </div>
                    {isActive && (
                      <CheckIcon
                        className="h-4 w-4 text-gray-500 flex-shrink-0"
                        aria-hidden="true"
                      />
                    )}
                  </button>
                )
              })}
          </div>
        </>
      )}
    </div>
  )
}
