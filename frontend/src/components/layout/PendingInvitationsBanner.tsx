/**
 * PendingInvitationsBanner - Shows pending organization invitations
 *
 * Displays a banner when the user has pending invitations to join organizations.
 * Users can accept or decline invitations directly from this banner.
 */

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  EnvelopeIcon,
  CheckIcon,
  XMarkIcon,
  BuildingOfficeIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline'
import { Button } from '@/components/ui'
import { organizationMembersApi, type PendingInvitation, type MemberRole } from '@/services/marketplace'
import { cn } from '@/utils/cn'
import toast from 'react-hot-toast'

const ROLE_LABELS: Record<MemberRole, string> = {
  owner: 'Owner',
  admin: 'Admin',
  member: 'Member',
  viewer: 'Viewer',
}

export function PendingInvitationsBanner() {
  const queryClient = useQueryClient()
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set())

  // Fetch pending invitations
  const { data: invitations = [], isLoading } = useQuery({
    queryKey: ['pending-invitations'],
    queryFn: () => organizationMembersApi.getMyPendingInvitations(),
    refetchInterval: 60000, // Refresh every minute
    staleTime: 30000,
  })

  // Accept invitation mutation
  const acceptMutation = useMutation({
    mutationFn: (token: string) => organizationMembersApi.acceptInvitation(token),
    onSuccess: (data) => {
      toast.success(`Joined ${data.organization.name} successfully!`)
      queryClient.invalidateQueries({ queryKey: ['pending-invitations'] })
      queryClient.invalidateQueries({ queryKey: ['auth'] })
      // Refresh page to update organization context
      window.location.reload()
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to accept invitation')
    },
  })

  // Decline invitation mutation
  const declineMutation = useMutation({
    mutationFn: (token: string) => organizationMembersApi.declineInvitation(token),
    onSuccess: () => {
      toast.success('Invitation declined')
      queryClient.invalidateQueries({ queryKey: ['pending-invitations'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to decline invitation')
    },
  })

  // Filter out dismissed invitations
  const visibleInvitations = invitations.filter((inv) => !dismissedIds.has(inv.id))

  // Don't render if loading or no invitations
  if (isLoading || visibleInvitations.length === 0) {
    return null
  }

  return (
    <div className="bg-gradient-to-r from-purple-600 to-indigo-600 text-white">
      <div className="container mx-auto px-4 py-3">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          {/* Left: Message */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-white/20 rounded-full flex items-center justify-center flex-shrink-0">
              <EnvelopeIcon className="w-5 h-5" />
            </div>
            <div>
              <p className="font-semibold text-sm sm:text-base">
                {visibleInvitations.length === 1
                  ? 'You have a pending invitation!'
                  : `You have ${visibleInvitations.length} pending invitations!`}
              </p>
              <p className="text-xs sm:text-sm text-white/80">
                {visibleInvitations.length === 1
                  ? `Join ${visibleInvitations[0].organization_name} as ${ROLE_LABELS[visibleInvitations[0].role]}`
                  : 'Accept to join organizations and collaborate with your team'}
              </p>
            </div>
          </div>

          {/* Right: Actions for single invitation or expand for multiple */}
          {visibleInvitations.length === 1 ? (
            <SingleInvitationActions
              invitation={visibleInvitations[0]}
              onAccept={() => acceptMutation.mutate(visibleInvitations[0].id)}
              onDecline={() => declineMutation.mutate(visibleInvitations[0].id)}
              isAccepting={acceptMutation.isPending}
              isDeclining={declineMutation.isPending}
            />
          ) : (
            <MultipleInvitationsView
              invitations={visibleInvitations}
              onAccept={(token) => acceptMutation.mutate(token)}
              onDecline={(token) => declineMutation.mutate(token)}
              onDismiss={(id) => setDismissedIds((prev) => new Set([...prev, id]))}
              isAccepting={acceptMutation.isPending}
              isDeclining={declineMutation.isPending}
            />
          )}
        </div>
      </div>
    </div>
  )
}

// Single invitation quick actions
function SingleInvitationActions({
  invitation,
  onAccept,
  onDecline,
  isAccepting,
  isDeclining,
}: {
  invitation: PendingInvitation
  onAccept: () => void
  onDecline: () => void
  isAccepting: boolean
  isDeclining: boolean
}) {
  return (
    <div className="flex items-center gap-2 flex-shrink-0">
      <Button
        variant="secondary"
        size="sm"
        onClick={onDecline}
        disabled={isDeclining || isAccepting}
        className="bg-white/20 text-white border-white/30 hover:bg-white/30 text-xs sm:text-sm"
      >
        {isDeclining ? (
          'Declining...'
        ) : (
          <>
            <XMarkIcon className="w-4 h-4 sm:mr-1" />
            <span className="hidden sm:inline">Decline</span>
          </>
        )}
      </Button>
      <Button
        variant="primary"
        size="sm"
        onClick={onAccept}
        disabled={isAccepting || isDeclining}
        className="bg-white text-purple-700 hover:bg-white/90 text-xs sm:text-sm"
      >
        {isAccepting ? (
          'Joining...'
        ) : (
          <>
            <CheckIcon className="w-4 h-4 sm:mr-1" />
            <span className="hidden sm:inline">Accept & Join</span>
            <span className="sm:hidden">Join</span>
          </>
        )}
      </Button>
    </div>
  )
}

// Multiple invitations expanded view
function MultipleInvitationsView({
  invitations,
  onAccept,
  onDecline,
  onDismiss,
  isAccepting,
  isDeclining,
}: {
  invitations: PendingInvitation[]
  onAccept: (token: string) => void
  onDecline: (token: string) => void
  onDismiss: (id: string) => void
  isAccepting: boolean
  isDeclining: boolean
}) {
  const [expanded, setExpanded] = useState(false)

  if (!expanded) {
    return (
      <Button
        variant="secondary"
        size="sm"
        onClick={() => setExpanded(true)}
        className="bg-white text-purple-700 hover:bg-white/90 text-xs sm:text-sm"
      >
        <UserGroupIcon className="w-4 h-4 mr-1" />
        View All ({invitations.length})
      </Button>
    )
  }

  return (
    <div className="w-full sm:w-auto mt-3 sm:mt-0">
      <div className="bg-white rounded-lg shadow-lg p-4 text-gray-900 max-h-64 overflow-y-auto">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-sm">Pending Invitations</h3>
          <button
            onClick={() => setExpanded(false)}
            className="text-gray-400 hover:text-gray-600"
          >
            <XMarkIcon className="w-4 h-4" />
          </button>
        </div>
        <div className="space-y-3">
          {invitations.map((invitation) => (
            <div
              key={invitation.id}
              className="flex items-center justify-between gap-3 p-2 bg-gray-50 rounded-lg"
            >
              <div className="flex items-center gap-2 min-w-0">
                <div className="w-8 h-8 bg-purple-100 rounded-full flex items-center justify-center flex-shrink-0">
                  <BuildingOfficeIcon className="w-4 h-4 text-purple-600" />
                </div>
                <div className="min-w-0">
                  <p className="font-medium text-sm truncate">
                    {invitation.organization_name}
                  </p>
                  <p className="text-xs text-gray-500">
                    as {ROLE_LABELS[invitation.role]}
                    {invitation.invited_by_name && ` • by ${invitation.invited_by_name}`}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <button
                  onClick={() => onDecline(invitation.id)}
                  disabled={isDeclining || isAccepting}
                  className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors"
                  title="Decline"
                >
                  <XMarkIcon className="w-4 h-4" />
                </button>
                <button
                  onClick={() => onAccept(invitation.id)}
                  disabled={isAccepting || isDeclining}
                  className="p-1.5 text-green-600 hover:bg-green-50 rounded transition-colors"
                  title="Accept"
                >
                  <CheckIcon className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
