/**
 * AddTeamServerModal - Add shared credentials for team servers (Admin only)
 *
 * Flow:
 * 1. Select a server from marketplace
 * 2. Configure credentials
 * 3. Set name, description, and visibility
 * 4. Create org credential
 */

import { useState, useEffect } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  XMarkIcon,
  MagnifyingGlassIcon,
  ServerIcon,
  EyeIcon,
  EyeSlashIcon,
  CheckCircleIcon,
  BuildingOffice2Icon,
  UsersIcon,
  LockClosedIcon,
} from '@heroicons/react/24/outline'
import { Button, Input, Alert } from '@/components/ui'
import { marketplaceApi, orgCredentialsApi } from '@/services/marketplace'
import type { MCPServer } from '@/types/marketplace'

interface AddTeamServerModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
}

type Step = 'select' | 'configure'

export function AddTeamServerModal({ isOpen, onClose, onSuccess }: AddTeamServerModalProps) {
  const [step, setStep] = useState<Step>('select')
  const [selectedServer, setSelectedServer] = useState<MCPServer | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [showValues, setShowValues] = useState<Record<string, boolean>>({})
  const [credentials, setCredentials] = useState<Record<string, string>>({})
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [visibleToUsers, setVisibleToUsers] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Fetch marketplace servers
  const { data: servers = [], isLoading: isLoadingServers } = useQuery({
    queryKey: ['marketplace-servers'],
    queryFn: () => marketplaceApi.listServers(),
    enabled: isOpen,
  })

  // Filter servers by search
  const filteredServers = servers.filter(
    (server) =>
      server.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      server.description?.toLowerCase().includes(searchQuery.toLowerCase())
  )

  // Create org credential mutation
  const createMutation = useMutation({
    mutationFn: async () => {
      if (!selectedServer) throw new Error('No server selected')
      return orgCredentialsApi.createOrgCredential(
        selectedServer.id,
        credentials,
        name,
        visibleToUsers
      )
    },
    onSuccess: () => {
      onSuccess()
      handleClose()
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : 'Failed to create team credential')
    },
  })

  // Reset state when modal opens/closes
  useEffect(() => {
    if (isOpen) {
      setStep('select')
      setSelectedServer(null)
      setSearchQuery('')
      setCredentials({})
      setName('')
      setDescription('')
      setVisibleToUsers(true)
      setError(null)
      setShowValues({})
    }
  }, [isOpen])

  const handleClose = () => {
    setStep('select')
    setSelectedServer(null)
    onClose()
  }

  const handleSelectServer = (server: MCPServer) => {
    setSelectedServer(server)
    setName(`${server.name} (Team)`)
    // Initialize credentials with empty values
    const initialCredentials: Record<string, string> = {}
    server.credentials?.forEach((field) => {
      initialCredentials[field.name] = ''
    })
    setCredentials(initialCredentials)
    setStep('configure')
  }

  const handleBack = () => {
    setStep('select')
    setSelectedServer(null)
    setError(null)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    // Validate required fields
    if (!name.trim()) {
      setError('Name is required')
      return
    }

    // Validate required credentials
    if (selectedServer?.credentials) {
      for (const field of selectedServer.credentials) {
        if (field.required && !credentials[field.name]?.trim()) {
          setError(`${field.name} is required`)
          return
        }
      }
    }

    createMutation.mutate()
  }

  const toggleShowValue = (fieldName: string) => {
    setShowValues((prev) => ({ ...prev, [fieldName]: !prev[fieldName] }))
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-gray-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                <BuildingOffice2Icon className="w-5 h-5 text-purple-600" />
              </div>
              <div>
                <h2 className="text-xl font-bold text-gray-900">Add Team Server</h2>
                <p className="text-sm text-gray-600">
                  {step === 'select' ? 'Select a server to share with your team' : `Configure ${selectedServer?.name}`}
                </p>
              </div>
            </div>
            <button onClick={handleClose} className="text-gray-400 hover:text-gray-600">
              <XMarkIcon className="w-6 h-6" />
            </button>
          </div>

          {/* Progress indicator */}
          <div className="flex items-center gap-2 mt-4">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
              step === 'select' ? 'bg-purple-600 text-white' : 'bg-green-500 text-white'
            }`}>
              {step === 'configure' ? <CheckCircleIcon className="w-4 h-4" /> : '1'}
            </div>
            <div className="flex-1 h-1 bg-gray-200 rounded">
              <div className={`h-full rounded transition-all bg-purple-600 ${step === 'configure' ? 'w-full' : 'w-0'}`} />
            </div>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
              step === 'configure' ? 'bg-purple-600 text-white' : 'bg-gray-200 text-gray-500'
            }`}>
              2
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {error && (
            <Alert variant="error" title="Error" className="mb-4" onClose={() => setError(null)}>
              {error}
            </Alert>
          )}

          {/* Step 1: Select Server */}
          {step === 'select' && (
            <div className="space-y-4">
              {/* Search */}
              <div className="relative">
                <MagnifyingGlassIcon className="w-5 h-5 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search servers..."
                  className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
                />
              </div>

              {/* Server List */}
              {isLoadingServers ? (
                <div className="text-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-2 border-gray-300 border-t-purple-600 mx-auto" />
                  <p className="text-sm text-gray-500 mt-2">Loading servers...</p>
                </div>
              ) : filteredServers.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <ServerIcon className="w-12 h-12 mx-auto mb-3 text-gray-300" />
                  <p>No servers found</p>
                </div>
              ) : (
                <div className="grid gap-3 max-h-96 overflow-y-auto">
                  {filteredServers.map((server) => (
                    <button
                      key={server.id}
                      onClick={() => handleSelectServer(server)}
                      className="flex items-start gap-3 p-4 border border-gray-200 rounded-lg hover:border-purple-300 hover:bg-purple-50 transition-colors text-left"
                    >
                      <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-purple-500 to-purple-600 flex items-center justify-center text-white font-bold flex-shrink-0">
                        {server.name.charAt(0)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-gray-900">{server.name}</p>
                        <p className="text-sm text-gray-500 line-clamp-2">{server.description}</p>
                        {server.requires_credentials && (
                          <span className="inline-flex items-center gap-1 mt-1 text-xs text-amber-600">
                            <LockClosedIcon className="w-3 h-3" />
                            Requires credentials
                          </span>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Step 2: Configure */}
          {step === 'configure' && selectedServer && (
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Info Alert */}
              <Alert variant="info" title="Team Credentials">
                These credentials will be shared with your team. Members will be able to use this
                server without providing their own credentials.
              </Alert>

              {/* Name & Description */}
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Name <span className="text-red-500">*</span>
                  </label>
                  <Input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g., Company Grist Account"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Description
                  </label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Optional description for your team"
                    rows={2}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
                  />
                </div>
              </div>

              {/* Visibility Toggle */}
              <div className="p-4 bg-gray-50 rounded-lg">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {visibleToUsers ? (
                      <UsersIcon className="w-5 h-5 text-purple-600" />
                    ) : (
                      <LockClosedIcon className="w-5 h-5 text-gray-500" />
                    )}
                    <div>
                      <p className="font-medium text-gray-900">
                        {visibleToUsers ? 'Visible to all members' : 'Admin only'}
                      </p>
                      <p className="text-xs text-gray-500">
                        {visibleToUsers
                          ? 'All team members can see and use this server'
                          : 'Only admins can see this credential (used as fallback)'}
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setVisibleToUsers(!visibleToUsers)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      visibleToUsers ? 'bg-purple-600' : 'bg-gray-300'
                    }`}
                  >
                    <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      visibleToUsers ? 'translate-x-6' : 'translate-x-1'
                    }`} />
                  </button>
                </div>
              </div>

              {/* Credential Fields */}
              {selectedServer.credentials && selectedServer.credentials.length > 0 && (
                <div className="space-y-4">
                  <h3 className="font-medium text-gray-900">Credentials</h3>
                  {selectedServer.credentials.map((field) => (
                    <div key={field.name}>
                      <div className="flex items-start justify-between mb-1">
                        <label className="block text-sm font-medium text-gray-700">
                          {field.name}
                          {field.required && <span className="text-red-500 ml-1">*</span>}
                        </label>
                        {field.documentation_url && (
                          <a
                            href={field.documentation_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-purple-600 hover:underline"
                          >
                            How to get this?
                          </a>
                        )}
                      </div>
                      <div className="relative">
                        <Input
                          type={field.type === 'secret' && !showValues[field.name] ? 'password' : 'text'}
                          value={credentials[field.name] || ''}
                          onChange={(e) => setCredentials({ ...credentials, [field.name]: e.target.value })}
                          placeholder={field.placeholder || `Enter ${field.name}`}
                          helperText={field.description}
                        />
                        {field.type === 'secret' && (
                          <button
                            type="button"
                            onClick={() => toggleShowValue(field.name)}
                            className="absolute right-3 top-2.5 text-gray-400 hover:text-gray-600"
                          >
                            {showValues[field.name] ? (
                              <EyeSlashIcon className="h-5 w-5" />
                            ) : (
                              <EyeIcon className="h-5 w-5" />
                            )}
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </form>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-gray-200 flex justify-between">
          {step === 'configure' && (
            <Button variant="ghost" onClick={handleBack}>
              Back
            </Button>
          )}
          <div className="flex gap-3 ml-auto">
            <Button variant="secondary" onClick={handleClose}>
              Cancel
            </Button>
            {step === 'configure' && (
              <Button
                variant="primary"
                onClick={handleSubmit}
                isLoading={createMutation.isPending}
                className="bg-purple-600 hover:bg-purple-700"
              >
                {createMutation.isPending ? 'Creating...' : 'Add Team Server'}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
