/**
 * Team Page
 *
 * Team settings including members, roles, and shared credentials.
 * Available to Team tier subscribers only.
 */

import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  BuildingOfficeIcon,
  UserGroupIcon,
  UserPlusIcon,
  TrashIcon,
  KeyIcon,
  EnvelopeIcon,
  XMarkIcon,
  ArrowPathIcon,
  ArrowsRightLeftIcon,
  EyeIcon,
  EyeSlashIcon,
} from '@heroicons/react/24/outline'
import { Button, Card } from '@/components/ui'
import { cn } from '@/utils/cn'
import { useOrganization, useAuth, useSubscription } from '@/hooks/useAuth'
import {
  organizationMembersApi,
  orgCredentialsApi,
  type OrganizationMember,
  type MemberRole,
  type Invitation,
  type OrganizationCredential,
} from '@/services/marketplace'
import toast from 'react-hot-toast'

interface UserOrganization {
  id: string
  name: string
  slug: string
  organization_type: string
  role: string
  joined_at: string | null
}

const ROLE_COLORS: Record<MemberRole, string> = {
  owner: 'bg-purple-100 text-purple-700',
  admin: 'bg-blue-100 text-blue-700',
  member: 'bg-green-100 text-green-700',
  viewer: 'bg-gray-100 text-gray-700',
}

export function TeamPage() {
  const { t } = useTranslation('settings')
  const { organization, organizationName, organizationId } = useOrganization()
  const { user, isCommunity, isCloudSaaS, editionLoading } = useAuth()
  const { tier } = useSubscription()
  const [members, setMembers] = useState<OrganizationMember[]>([])
  const [invitations, setInvitations] = useState<Invitation[]>([])
  const [sharedCredentials, setSharedCredentials] = useState<OrganizationCredential[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showInviteModal, setShowInviteModal] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState<MemberRole>('member')
  const [isInviting, setIsInviting] = useState(false)

  // Organization switcher state
  const [userOrganizations, setUserOrganizations] = useState<UserOrganization[]>([])
  const [loadingOrgs, setLoadingOrgs] = useState(true)
  const [switching, setSwitching] = useState(false)
  const [switchError, setSwitchError] = useState<string | null>(null)

  // Community edition: team features not available
  if (editionLoading) {
    return (
      <div className="container py-8">
        <div className="text-center text-gray-600">{t('team.loading')}</div>
      </div>
    )
  }

  if (isCommunity) {
    return (
      <div className="container py-8">
        <Card className="max-w-2xl mx-auto p-8 text-center">
          <UserGroupIcon className="w-16 h-16 text-gray-400 mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-gray-900 mb-2">
            {t('team.communityTitle')}
          </h2>
          <p className="text-gray-600 mb-6">
            {t('team.communityDescription')}
          </p>
          <a
            href="https://bigmcp.cloud/welcome#pricing"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-block bg-orange hover:bg-orange-dark text-white font-medium py-2 px-6 rounded-lg transition-colors"
          >
            {t('team.viewEnterprisePlans')}
          </a>
        </Card>
      </div>
    )
  }

  // SaaS Individual: upgrade to Team required
  if (isCloudSaaS && tier === 'individual') {
    return (
      <div className="container py-8">
        <Card className="max-w-2xl mx-auto p-8">
          <div className="flex items-start gap-4">
            <div className="flex-shrink-0">
              <UserGroupIcon className="w-12 h-12 text-blue-600" />
            </div>
            <div className="flex-1">
              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                {t('team.upgradeToTeam')}
              </h2>
              <p className="text-gray-600 mb-4">
                {t('team.individualPlanDescription')}
              </p>
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
                <h3 className="font-semibold text-blue-900 mb-2">{t('team.teamPlanIncludes')}</h3>
                <ul className="space-y-1 text-sm text-blue-700">
                  <li>✓ {t('team.teamFeatures.unlimitedMembers')}</li>
                  <li>✓ {t('team.teamFeatures.roleBasedAccess')}</li>
                  <li>✓ {t('team.teamFeatures.sharedCredentials')}</li>
                  <li>✓ {t('team.teamFeatures.teamInvitations')}</li>
                  <li>✓ {t('team.teamFeatures.allIndividualFeatures')}</li>
                </ul>
              </div>
              <a
                href="/settings/subscription"
                className="inline-block bg-blue-600 hover:bg-blue-700 text-white font-medium py-2 px-6 rounded-lg transition-colors"
              >
                {t('team.upgradeToTeamButton')}
              </a>
            </div>
          </div>
        </Card>
      </div>
    )
  }

  // Load organization data
  const loadData = useCallback(async () => {
    if (!organizationId) return

    setIsLoading(true)
    try {
      // Load members and credentials - accessible to all members
      const [membersRes, credentialsRes] = await Promise.all([
        organizationMembersApi.listMembers(organizationId),
        orgCredentialsApi.listOrgCredentials(),
      ])

      setMembers(membersRes.members)
      setSharedCredentials(credentialsRes)

      // Check if current user is admin/owner
      const currentUserMember = membersRes.members.find((m: OrganizationMember) => m.user_id === user?.id)
      const isAdmin = currentUserMember?.role === 'owner' || currentUserMember?.role === 'admin'

      // Load invitations only for admins (non-admins get 403)
      if (isAdmin) {
        try {
          const invitationsRes = await organizationMembersApi.listInvitations(organizationId, 'pending')
          setInvitations(invitationsRes)
        } catch {
          setInvitations([])
        }
      } else {
        setInvitations([])
      }
    } catch (error) {
      console.error('Failed to load organization data:', error)
      toast.error('Failed to load organization data')
    } finally {
      setIsLoading(false)
    }
  }, [organizationId, user?.id])

  useEffect(() => {
    loadData()
  }, [loadData])

  // Fetch all user organizations for switcher
  useEffect(() => {
    fetchUserOrganizations()
  }, [])

  const fetchUserOrganizations = async () => {
    try {
      const token = localStorage.getItem('bigmcp_access_token')
      const response = await fetch('/api/v1/auth/organizations', {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })

      if (response.ok) {
        const data = await response.json()
        setUserOrganizations(data.organizations || [])
      }
    } catch (error) {
      console.error('Failed to fetch organizations:', error)
    } finally {
      setLoadingOrgs(false)
    }
  }

  const handleSwitchOrganization = async (newOrgId: string) => {
    if (!newOrgId || newOrgId === organizationId) {
      return
    }

    setSwitching(true)
    setSwitchError(null)

    try {
      const token = localStorage.getItem('bigmcp_access_token')
      const response = await fetch(`/api/v1/auth/switch-organization?organization_id=${newOrgId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
      })

      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.detail || 'Failed to switch organization')
      }

      const data = await response.json()

      // Save new tokens (use same keys as AuthContext)
      localStorage.setItem('bigmcp_access_token', data.access_token)
      localStorage.setItem('bigmcp_refresh_token', data.refresh_token)

      // Reload the page to refresh all context
      window.location.reload()
    } catch (error: any) {
      setSwitchError(error.message || 'Failed to switch organization')
      setSwitching(false)
    }
  }

  const handleInviteMember = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!organizationId || !inviteEmail.trim()) return

    setIsInviting(true)
    try {
      await organizationMembersApi.invite(organizationId, inviteEmail.trim(), inviteRole)
      toast.success(`Invitation sent to ${inviteEmail}`)
      setInviteEmail('')
      setInviteRole('member')
      setShowInviteModal(false)
      loadData()
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to send invitation')
    } finally {
      setIsInviting(false)
    }
  }

  const handleRemoveMember = async (memberId: string, userId: string) => {
    if (!organizationId) return
    if (!confirm(t('team.removeConfirm'))) return

    try {
      await organizationMembersApi.removeMember(organizationId, userId)
      toast.success('Member removed')
      setMembers((prev) => prev.filter((m) => m.id !== memberId))
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to remove member')
    }
  }

  const handleChangeRole = async (userId: string, newRole: MemberRole) => {
    if (!organizationId) return

    try {
      const updated = await organizationMembersApi.updateRole(organizationId, userId, newRole)
      toast.success('Role updated')
      setMembers((prev) =>
        prev.map((m) => (m.user_id === userId ? { ...m, role: updated.role } : m))
      )
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to update role')
    }
  }

  const handleRevokeInvitation = async (invitationId: string) => {
    if (!organizationId) return
    if (!confirm(t('team.revokeConfirm'))) return

    try {
      await organizationMembersApi.revokeInvitation(organizationId, invitationId)
      toast.success('Invitation revoked')
      setInvitations((prev) => prev.filter((i) => i.id !== invitationId))
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to revoke invitation')
    }
  }

  // Check if current user is admin/owner
  const currentMember = members.find((m) => m.user_id === user?.id)
  const canManageMembers = currentMember?.role === 'owner' || currentMember?.role === 'admin'

  // Toggle visibility for shared credential
  const handleToggleCredentialVisibility = async (serverId: string, currentVisibility: boolean) => {
    try {
      await orgCredentialsApi.updateOrgCredential(serverId, {
        visible_to_users: !currentVisibility,
      })
      setSharedCredentials((prev) =>
        prev.map((c) =>
          c.server_id === serverId ? { ...c, visible_to_users: !currentVisibility } : c
        )
      )
      toast.success(t('team.credentialVisibilityUpdated'))
    } catch (error: any) {
      toast.error(error.response?.data?.detail || t('team.credentialVisibilityFailed'))
    }
  }

  // Delete shared credential
  const handleDeleteCredential = async (serverId: string, credentialName: string) => {
    if (!confirm(t('team.deleteCredentialConfirm', { name: credentialName }))) return

    try {
      await orgCredentialsApi.deleteOrgCredential(serverId)
      setSharedCredentials((prev) => prev.filter((c) => c.server_id !== serverId))
      toast.success(t('team.credentialDeleted'))
    } catch (error: any) {
      toast.error(error.response?.data?.detail || t('team.credentialDeleteFailed'))
    }
  }

  return (
    <div className="container py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-gray-900 mb-2">{t('team.title')}</h1>
        <p className="text-lg text-gray-600 font-serif">
          {t('team.subtitle')}
        </p>
      </div>

      {/* SaaS Team: Billing Tracker */}
      {isCloudSaaS && tier === 'team' && (
        <Card padding="lg" className="mb-6 bg-gradient-to-r from-green-50 to-blue-50 border-green-200">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-gray-900 mb-1">
                {t('team.billingTracker.title')}
              </h3>
              <p className="text-sm text-gray-600">
                {t('team.billingTracker.currentlyBilling')} <span className="font-medium text-green-700">{members.length} {t('team.members').toLowerCase()}</span> {t('team.billingTracker.atRate')}
              </p>
            </div>
            <div className="text-right">
              <p className="text-3xl font-bold text-green-700">
                €{(members.length * 4.99).toFixed(2)}
              </p>
              <p className="text-xs text-gray-600">{t('team.billingTracker.perMonth')}</p>
            </div>
          </div>
        </Card>
      )}

      {/* Organization Switcher */}
      <Card padding="lg" className="mb-6">
        <div className="flex items-center gap-3 mb-4">
          <ArrowsRightLeftIcon className="w-6 h-6 text-gray-600" />
          <h2 className="text-lg font-semibold text-gray-900">{t('team.currentTeam')}</h2>
        </div>

        {loadingOrgs ? (
          <div className="flex items-center gap-2 text-gray-500">
            <ArrowPathIcon className="w-5 h-5 animate-spin" />
            <span>{t('team.loadingOrgs')}</span>
          </div>
        ) : userOrganizations.length > 1 ? (
          <div className="space-y-3">
            <p className="text-sm text-gray-600">
              {t('team.multiOrgHint')}
            </p>
            <div className="space-y-2">
              {userOrganizations.map((org) => (
                <label
                  key={org.id}
                  className={cn(
                    'flex items-center justify-between p-4 rounded-lg border-2 cursor-pointer transition-colors',
                    organizationId === org.id
                      ? 'border-orange bg-orange-50'
                      : 'border-gray-200 hover:border-orange-200'
                  )}
                  onClick={() => org.id !== organizationId && handleSwitchOrganization(org.id)}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-orange-100 rounded-full flex items-center justify-center">
                      <BuildingOfficeIcon className="w-6 h-6 text-orange" />
                    </div>
                    <div>
                      <p className="font-medium text-gray-900">{org.name}</p>
                      <p className="text-sm text-gray-500">
                        {org.organization_type === 'PERSONAL' ? t('team.personal') : t('team.title')} • {t(`team.roles.${org.role}`)}
                      </p>
                    </div>
                  </div>
                  {organizationId === org.id && (
                    <span className="text-xs font-medium text-orange bg-orange-100 px-2 py-1 rounded">
                      {t('team.current')}
                    </span>
                  )}
                  {switching && org.id !== organizationId && (
                    <ArrowPathIcon className="w-4 h-4 animate-spin text-gray-400" />
                  )}
                </label>
              ))}
            </div>
            {switchError && (
              <div className="text-sm text-red-600 bg-red-50 p-3 rounded-lg">
                {switchError}
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 bg-orange-100 rounded-full flex items-center justify-center">
              <BuildingOfficeIcon className="w-10 h-10 text-orange" />
            </div>
            <div>
              <h3 className="text-xl font-semibold text-gray-900">
                {organizationName || t('team.myTeam')}
              </h3>
              <p className="text-sm text-gray-600">
                {organization?.slug ? `@${organization.slug}` : t('team.noSlug')}
              </p>
            </div>
          </div>
        )}
      </Card>

      {/* Members Section */}
      <Card padding="lg" className="mb-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <UserGroupIcon className="w-6 h-6 text-gray-600" />
            <h2 className="text-lg font-semibold text-gray-900">{t('team.members')} ({members.length})</h2>
          </div>
          {canManageMembers && (
            <Button variant="primary" onClick={() => setShowInviteModal(true)}>
              <UserPlusIcon className="w-5 h-5 mr-2" />
              {t('team.invite')}
            </Button>
          )}
        </div>

        {isLoading ? (
          <div className="text-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-2 border-gray-300 border-t-orange mx-auto" />
          </div>
        ) : members.length === 0 ? (
          <div className="text-center py-8">
            <UserGroupIcon className="w-10 h-10 text-gray-400 mx-auto mb-3" />
            <p className="text-gray-600 font-serif">{t('team.empty')}</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {members.map((member) => {
              const roleColor = ROLE_COLORS[member.role]
              const memberName = member.user_name || member.user_email || 'Unknown'
              return (
                <div key={member.id} className="py-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-gray-100 rounded-full flex items-center justify-center">
                      <span className="text-lg font-medium text-gray-600">
                        {memberName.charAt(0).toUpperCase()}
                      </span>
                    </div>
                    <div>
                      <p className="font-medium text-gray-900">{memberName}</p>
                      <p className="text-sm text-gray-500">{member.user_email}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    {canManageMembers && member.role !== 'owner' ? (
                      <select
                        value={member.role}
                        onChange={(e) => handleChangeRole(member.user_id, e.target.value as MemberRole)}
                        className="text-xs border border-gray-200 rounded px-2 py-1 bg-white"
                      >
                        <option value="admin">{t('team.roles.admin')}</option>
                        <option value="member">{t('team.roles.member')}</option>
                        <option value="viewer">{t('team.roles.viewer')}</option>
                      </select>
                    ) : (
                      <span className={cn('px-2 py-1 rounded text-xs font-medium', roleColor)}>
                        {t(`team.roles.${member.role}`)}
                      </span>
                    )}
                    {canManageMembers && member.role !== 'owner' && member.user_id !== user?.id && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveMember(member.id, member.user_id)}
                        className="text-red-600 hover:text-red-700"
                      >
                        <TrashIcon className="w-4 h-4" />
                      </Button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {/* Pending Invitations */}
        {invitations.length > 0 && (
          <div className="mt-6 pt-6 border-t border-gray-100">
            <h3 className="text-sm font-medium text-gray-700 mb-4 flex items-center gap-2">
              <EnvelopeIcon className="w-4 h-4" />
              {t('team.invitations')} ({invitations.length})
            </h3>
            <div className="space-y-3">
              {invitations.map((invitation) => (
                <div
                  key={invitation.id}
                  className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                >
                  <div>
                    <p className="text-sm font-medium text-gray-900">{invitation.email}</p>
                    <p className="text-xs text-gray-500">
                      {t('team.invitedAs')} {t(`team.roles.${invitation.role}`)} • {t('team.expires')}{' '}
                      {new Date(invitation.expires_at).toLocaleDateString()}
                    </p>
                  </div>
                  {canManageMembers && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRevokeInvitation(invitation.id)}
                      className="text-red-600 hover:text-red-700"
                    >
                      <XMarkIcon className="w-4 h-4" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* Shared Credentials Section */}
      <Card padding="lg">
        <div className="flex items-center gap-3 mb-6">
          <KeyIcon className="w-6 h-6 text-gray-600" />
          <h2 className="text-lg font-semibold text-gray-900">
            {t('team.sharedCredentials')} ({sharedCredentials.length})
          </h2>
        </div>

        {sharedCredentials.length === 0 ? (
          <div className="text-center py-8">
            <KeyIcon className="w-10 h-10 text-gray-400 mx-auto mb-3" />
            <p className="text-gray-600 font-serif">
              {t('team.noCredentials')}
            </p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {sharedCredentials.map((cred) => (
              <div key={cred.id} className="py-4 flex items-center justify-between">
                <div>
                  <p className="font-medium text-gray-900">{cred.name}</p>
                  <p className="text-sm text-gray-500">{t('team.server')}: {cred.server_id}</p>
                </div>
                <div className="flex items-center gap-3">
                  {/* Visibility Toggle (Admin only) */}
                  {canManageMembers ? (
                    <button
                      onClick={() => handleToggleCredentialVisibility(cred.server_id, cred.visible_to_users)}
                      className={cn(
                        'flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                        cred.visible_to_users
                          ? 'bg-green-100 text-green-700 hover:bg-green-200'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      )}
                      title={cred.visible_to_users ? t('team.clickToHide') : t('team.clickToShow')}
                    >
                      {cred.visible_to_users ? (
                        <>
                          <EyeIcon className="w-4 h-4" />
                          {t('team.visibleToMembers')}
                        </>
                      ) : (
                        <>
                          <EyeSlashIcon className="w-4 h-4" />
                          {t('team.adminOnly')}
                        </>
                      )}
                    </button>
                  ) : (
                    <span
                      className={cn(
                        'px-2 py-1 rounded text-xs font-medium',
                        cred.visible_to_users
                          ? 'bg-green-100 text-green-700'
                          : 'bg-gray-100 text-gray-700'
                      )}
                    >
                      {cred.visible_to_users ? t('team.visibleToMembers') : t('team.adminOnly')}
                    </span>
                  )}
                  {/* Delete Button (Admin only) */}
                  {canManageMembers && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDeleteCredential(cred.server_id, cred.name || 'credential')}
                      className="text-red-600 hover:text-red-700 hover:bg-red-50"
                      title={t('team.deleteCredential')}
                    >
                      <TrashIcon className="w-4 h-4" />
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Invite Modal */}
      {showInviteModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">{t('team.inviteModalTitle')}</h3>
              <button
                onClick={() => setShowInviteModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <XMarkIcon className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleInviteMember}>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    {t('team.inviteEmail')}
                  </label>
                  <input
                    type="email"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    placeholder={t('team.invitePlaceholder')}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{t('team.inviteRole')}</label>
                  <select
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value as MemberRole)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange"
                  >
                    <option value="admin">{t('team.roleDescriptions.admin')}</option>
                    <option value="member">{t('team.roleDescriptions.member')}</option>
                    <option value="viewer">{t('team.roleDescriptions.viewer')}</option>
                  </select>
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setShowInviteModal(false)}
                  className="flex-1"
                >
                  {t('account.cancel')}
                </Button>
                <Button type="submit" variant="primary" className="flex-1" isLoading={isInviting}>
                  {t('team.sendInvitation')}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
