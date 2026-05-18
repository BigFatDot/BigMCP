/**
 * Team admin hook.
 *
 * A user is "team admin" when they hold an ``admin`` or ``owner`` role
 * in at least one organization membership — exactly mirroring the
 * backend ``require_admin`` dependency. Instance admins are implicitly
 * team admins everywhere via the override.
 *
 * Use this to gate UI for surfaces that ``require_admin`` protects on
 * the backend (e.g. ``/admin/org/default-pool``). For instance-only
 * surfaces (Users, Audit logs, Server access, OAuth clients, SSO
 * providers, Compositions review/metrics, Instance branding), keep the
 * ``user.is_instance_admin`` check.
 */

import { useMemo } from 'react'
import { useAuth } from '../contexts/AuthContext'
import type { UserRole } from '../types/auth'

const ADMIN_ROLES: ReadonlySet<UserRole> = new Set(['admin', 'owner'])

export function useTeamAdmin(): boolean {
  const { user } = useAuth()

  return useMemo(() => {
    if (!user) return false
    if (user.is_instance_admin) return true
    return (user.organization_memberships ?? []).some((m) =>
      ADMIN_ROLES.has(m.role),
    )
  }, [user])
}
