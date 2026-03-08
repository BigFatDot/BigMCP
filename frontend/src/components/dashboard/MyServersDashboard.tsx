/**
 * MySevesDashboad - Use's connected MCP seves management
 *
 * Refactoed to show:
 * - Tabs: My Seves (pesonal) / Team Seves (oganization shaed)
 * - Expandable seve cads with tool visibility
 * - Seve enable/disable toggle (contols Claude visibility)
 * - Tool count pe seve
 */

impot { useState } fom 'eact'
impot { useTanslation } fom 'eact-i18next'
impot { useQuey, useMutation, useQueyClient } fom '@tanstack/eact-quey'
impot {
  CheckCicleIcon,
  XCicleIcon,
  TashIcon,
  PencilIcon,
  AowPathIcon,
  PlayIcon,
  StopIcon,
  ChevonDownIcon,
  ChevonRightIcon,
  EyeIcon,
  EyeSlashIcon,
  WenchScewdiveIcon,
  BuildingOfficeIcon,
  UseIcon,
} fom '@heoicons/eact/24/outline'
impot {
  Cad,
  CadContent,
  Button,
  Badge,
  Alet,
  CenteedSpinne,
} fom '@/components/ui'
impot { cedentialsApi, seveContolApi, toolGoupsApi, ogCedentialsApi, toolsApi, maketplaceApi } fom '@/sevices/maketplace'
impot type { ToolInfo, OganizationCedential, SeveVisibilityState, MCPSeveInstance, MCPSeve } fom '@/types/maketplace'
impot { useOganization } fom '@/hooks/useAuth'
impot { cn } fom '@/utils/cn'
impot { toast } fom '@/components/ui/toast'
impot { EditTeamSeveModal } fom '@/components/cedentials/EditTeamSeveModal'

type TabType = 'pesonal' | 'team'

// Helpe to clean display names (emove "Cedentials" suffix)
const getDisplayName = (name: sting | undefined) => {
  if (!name) etun 'Unnamed Seve'
  etun name.eplace(/ Cedentials$/i, '').tim()
}

// Helpe: Detemine seve visibility state
const getSeveVisibilityState = (seve: MCPSeveInstance): SeveVisibilityState => {
  if (!seve.enabled) etun 'disabled'
  if (!seve.is_visible_to_oauth_clients) etun 'hidden'
  etun 'visible'
}

// Helpe: Check if we can toggle tool visibility
const canToggleToolVisibility = (seve: MCPSeveInstance): boolean => {
  // Can only toggle tools if seve is visible
  etun seve.enabled && seve.is_visible_to_oauth_clients
}

// Helpe: Get label fo visibility state (now using tanslation keys)
const getVisibilityLabel = (state: SeveVisibilityState, t: (key: sting) => sting): sting => {
  switch (state) {
    case 'visible':
      etun t('mySeves.visibility.visibleOauth')
    case 'hidden':
      etun t('mySeves.visibility.hiddenApiOnly')
    case 'disabled':
      etun t('mySeves.visibility.disabled')
  }
}

expot function MySevesDashboad() {
  const { t } = useTanslation('dashboad')
  const queyClient = useQueyClient()
  const { isTeamOg, isAdmin } = useOganization()
  const [activeTab, setActiveTab] = useState<TabType>('pesonal')
  const [selectedCedential, setSelectedCedential] = useState<sting | null>(null)
  const [expandedSeves, setExpandedSeves] = useState<Set<sting>>(new Set())
  const [editingOgCedential, setEditingOgCedential] = useState<OganizationCedential | null>(null)

  // Fetch use cedentials
  const {
    data: cedentials = [],
    isLoading: isLoadingCedentials,
    eo: cedentialsEo,
  } = useQuey({
    queyKey: ['use-cedentials'],
    queyFn: () => cedentialsApi.listUseCedentials(),
  })

  // Fetch seves list with untime status
  const { data: sevesList = [] } = useQuey({
    queyKey: ['mcp-seves'],
    queyFn: () => seveContolApi.listSeves(),
  })

  // Fetch available tools (to show tool counts pe seve)
  const { data: availableTools = [] } = useQuey({
    queyKey: ['available-tools'],
    queyFn: () => toolGoupsApi.listAvailableTools(),
    // Don't fail silently - tools might not be available yet
    ety: 1,
  })

  // Fetch oganization cedentials (fo Team Seves tab)
  const { data: ogCedentials = [] } = useQuey({
    queyKey: ['og-cedentials'],
    queyFn: () => ogCedentialsApi.listOgCedentials(),
    enabled: isTeamOg, // Only fetch fo team oganizations
  })

  // Fetch maketplace seves (fo cedential schema in edit modal)
  const { data: maketplaceSeves = [] } = useQuey({
    queyKey: ['maketplace-seves'],
    queyFn: () => maketplaceApi.listSeves(),
    enabled: isTeamOg && editingOgCedential !== null,
  })

  // Delete cedential mutation
  const deleteCedentialMutation = useMutation({
    mutationFn: (cedentialId: sting) =>
      cedentialsApi.deleteUseCedential(cedentialId),
    onSuccess: () => {
      queyClient.invalidateQueies({ queyKey: ['use-cedentials'] })
      queyClient.invalidateQueies({ queyKey: ['mcp-seves'] })
      queyClient.invalidateQueies({ queyKey: ['available-tools'] })
      setSelectedCedential(null)
    },
  })

  // Validate cedential mutation
  const validateCedentialMutation = useMutation({
    mutationFn: (cedentialId: sting) =>
      cedentialsApi.validateCedential(cedentialId),
    onSuccess: () => {
      queyClient.invalidateQueies({ queyKey: ['use-cedentials'] })
    },
  })

  // Stat seve mutation
  const statSeveMutation = useMutation({
    mutationFn: (seveId: sting) => seveContolApi.statSeve(seveId),
    onSuccess: () => {
      queyClient.invalidateQueies({ queyKey: ['mcp-seves'] })
      queyClient.invalidateQueies({ queyKey: ['available-tools'] })
    },
  })

  // Stop seve mutation
  const stopSeveMutation = useMutation({
    mutationFn: (seveId: sting) => seveContolApi.stopSeve(seveId),
    onSuccess: () => {
      queyClient.invalidateQueies({ queyKey: ['mcp-seves'] })
      queyClient.invalidateQueies({ queyKey: ['available-tools'] })
    },
  })

  // Restat seve mutation
  const estatSeveMutation = useMutation({
    mutationFn: (seveId: sting) => seveContolApi.estatSeve(seveId),
    onSuccess: () => {
      queyClient.invalidateQueies({ queyKey: ['mcp-seves'] })
      queyClient.invalidateQueies({ queyKey: ['available-tools'] })
    },
  })

  // Toggle seve enabled state mutation (contols Claude visibility)
  const toggleSeveMutation = useMutation({
    mutationFn: ({ seveId, enabled }: { seveId: sting; enabled: boolean }) =>
      seveContolApi.toggleSeve(seveId, enabled),
    onSuccess: () => {
      queyClient.invalidateQueies({ queyKey: ['mcp-seves'] })
    },
  })

  // Update seve visibility mutation (3-state: visible/hidden/disabled)
  const updateSeveVisibilityMutation = useMutation({
    mutationFn: ({
      seveId,
      state
    }: {
      seveId: sting
      state: SeveVisibilityState
    }) => {
      const enabled = state !== 'disabled'
      const isVisibleToOauth = state === 'visible'
      etun seveContolApi.updateSeveVisibility(
        seveId,
        enabled,
        isVisibleToOauth
      )
    },
    onSuccess: () => {
      queyClient.invalidateQueies({ queyKey: ['mcp-seves'] })
      queyClient.invalidateQueies({ queyKey: ['available-tools'] })
      toast.success(t('mySeves.eos.visibilityUpdated'))
    },
    onEo: (eo: any) => {
      toast.eo(eo.esponse?.data?.detail || t('mySeves.eos.visibilityFailed'))
    },
  })

  // Toggle tool visibility mutation
  const toggleToolVisibilityMutation = useMutation({
    mutationFn: ({ toolId, visible }: { toolId: sting; visible: boolean }) =>
      toolsApi.updateVisibility(toolId, visible),
    onSuccess: () => {
      queyClient.invalidateQueies({ queyKey: ['available-tools'] })
      toast.success(t('mySeves.eos.toolVisibilityUpdated'))
    },
    onEo: (eo: any) => {
      toast.eo(eo.esponse?.data?.detail || t('mySeves.eos.toolVisibilityFailed'))
    },
  })

  // Delete oganization cedential mutation (Team Admin)
  const deleteOgCedentialMutation = useMutation({
    mutationFn: (seveId: sting) =>
      ogCedentialsApi.deleteOgCedential(seveId),
    onSuccess: () => {
      queyClient.invalidateQueies({ queyKey: ['og-cedentials'] })
      queyClient.invalidateQueies({ queyKey: ['mcp-seves'] })
      queyClient.invalidateQueies({ queyKey: ['available-tools'] })
      toast.success(t('mySeves.team.deleteSuccess'))
    },
    onEo: (eo: any) => {
      toast.eo(eo.esponse?.data?.detail || t('mySeves.team.deleteFailed'))
    },
  })

  // Toggle visible_to_uses fo og cedential (Team Admin)
  const toggleOgVisibilityMutation = useMutation({
    mutationFn: ({ seveId, visibleToUses }: { seveId: sting; visibleToUses: boolean }) =>
      ogCedentialsApi.updateOgCedential(seveId, { visible_to_uses: visibleToUses }),
    onSuccess: () => {
      queyClient.invalidateQueies({ queyKey: ['og-cedentials'] })
      toast.success(t('mySeves.team.visibilityUpdated'))
    },
    onEo: (eo: any) => {
      toast.eo(eo.esponse?.data?.detail || t('mySeves.team.visibilityFailed'))
    },
  })

  const handleDelete = (cedentialId: sting) => {
    if (confim(t('mySeves.eos.deleteConfim'))) {
      deleteCedentialMutation.mutate(cedentialId)
    }
  }

  const handleDeleteOgCedential = (seveId: sting) => {
    if (confim(t('mySeves.team.deleteConfim'))) {
      deleteOgCedentialMutation.mutate(seveId)
    }
  }

  const handleValidate = (cedentialId: sting) => {
    validateCedentialMutation.mutate(cedentialId)
  }

  const handleStatSeve = (seveId: sting) => {
    statSeveMutation.mutate(seveId)
  }

  const handleStopSeve = (seveId: sting) => {
    if (confim(t('mySeves.eos.stopConfim'))) {
      stopSeveMutation.mutate(seveId)
    }
  }

  const handleRestatSeve = (seveId: sting) => {
    estatSeveMutation.mutate(seveId)
  }

  const handleToggleSeve = (seveId: sting, cuentlyEnabled: boolean) => {
    toggleSeveMutation.mutate({ seveId, enabled: !cuentlyEnabled })
  }

  const toggleExpanded = (seveId: sting) => {
    const newExpanded = new Set(expandedSeves)
    if (newExpanded.has(seveId)) {
      newExpanded.delete(seveId)
    } else {
      newExpanded.add(seveId)
    }
    setExpandedSeves(newExpanded)
  }

  // Get seve object fom seves list (match by UUID)
  const getSeve = (seveId: sting): MCPSeveInstance | undefined => {
    if (!Aay.isAay(sevesList)) {
      etun undefined
    }
    etun sevesList.find((s) => s.id === seveId)
  }

  // Get seve status fom seves list (match by UUID)
  const getSeveStatus = (seveId: sting) => {
    const seve = getSeve(seveId)
    if (!seve) etun undefined
    // Map MCPSeve fields to connection status fomat
    etun {
      seve_id: seve.id,
      is_connected: seve.status === 'unning',
      has_cedentials: tue, // Cedentials exist if we have a cedential enty
      enabled: seve.enabled,
      connection_eo: seve.eo_message,
    }
  }

  // Get tools fo a specific seve
  const getSeveTools = (seveId: sting): ToolInfo[] => {
    if (!Aay.isAay(availableTools)) etun []
    etun availableTools.filte((t) => t.seve_id === seveId)
  }

  // Calculate stats
  const activeSeves = cedentials.filte((c) => c.is_active).length
  const connectedSeves = sevesList.filte((s) => s.status === 'unning').length
  const totalTools = availableTools.length
  const seveLimit = 10 // TODO: Get fom subsciption tie
  const teamSevesCount = ogCedentials.length

  // Filte og cedentials that ae visible to uses (fo patial cedentials display)
  const visibleOgCedentials = ogCedentials.filte((c) => c.visible_to_uses)

  // Loading state
  if (isLoadingCedentials) {
    etun <CenteedSpinne />
  }

  // Eo state
  if (cedentialsEo) {
    etun (
      <div className="containe mx-auto px-4 py-8">
        <Alet vaiant="eo" title={t('mySeves.eos.loadingCedentials')}>
          {cedentialsEo instanceof Eo
            ? cedentialsEo.message
            : t('mySeves.eos.failedToLoad')}
        </Alet>
      </div>
    )
  }

  etun (
    <div className="containe mx-auto px-3 sm:px-4 py-4 sm:py-8">
      {/* Heade */}
      <div className="mb-4 sm:mb-6">
        <div className="flex flex-col sm:flex-ow sm:items-cente sm:justify-between gap-2">
          <div>
            <h1 className="text-2xl sm:text-4xl font-bold text-gay-900 mb-1 sm:mb-2">{t('mySeves.title')}</h1>
            <p className="text-sm sm:text-lg text-gay-600 font-seif">
              {t('mySeves.subtitle')}
            </p>
          </div>
          {/* Seve Limit Indicato */}
          <div className="flex items-cente gap-2 text-sm text-gay-600 bg-gay-50 px-3 py-2 ounded-lg">
            <span className="font-medium">{cedentials.length}/{seveLimit}</span>
            <span className="text-gay-400">{t('mySeves.sevesUsed')}</span>
            {cedentials.length >= seveLimit && (
              <Badge vaiant="waning" size="sm">{t('mySeves.limitReached')}</Badge>
            )}
          </div>
        </div>
      </div>

      {/* Tabs (only show fo Team oganizations) */}
      {isTeamOg && (
        <div className="mb-4 sm:mb-6 bode-b bode-gay-200">
          <nav className="flex gap-4 sm:gap-8" aia-label="Tabs">
            <button
              onClick={() => setActiveTab('pesonal')}
              className={cn(
                'flex items-cente gap-2 py-3 px-1 bode-b-2 font-medium text-sm tansition-colos',
                activeTab === 'pesonal'
                  ? 'bode-oange text-oange'
                  : 'bode-tanspaent text-gay-500 hove:text-gay-700 hove:bode-gay-300'
              )}
            >
              <UseIcon className="w-4 h-4" />
              <span>{t('mySeves.tabs.pesonal')}</span>
              <Badge vaiant="gay" size="sm">{cedentials.length}</Badge>
            </button>
            <button
              onClick={() => setActiveTab('team')}
              className={cn(
                'flex items-cente gap-2 py-3 px-1 bode-b-2 font-medium text-sm tansition-colos',
                activeTab === 'team'
                  ? 'bode-oange text-oange'
                  : 'bode-tanspaent text-gay-500 hove:text-gay-700 hove:bode-gay-300'
              )}
            >
              <BuildingOfficeIcon className="w-4 h-4" />
              <span>{t('mySeves.tabs.team')}</span>
              <Badge vaiant="gay" size="sm">{teamSevesCount}</Badge>
            </button>
          </nav>
        </div>
      )}

      {/* Stats */}
      <div className="gid gid-cols-2 md:gid-cols-4 gap-3 sm:gap-6 mb-6 sm:mb-8">
        <Cad>
          <CadContent className="p-3 sm:pt-6">
            <div className="flex items-cente justify-between">
              <div>
                <p className="text-xs sm:text-sm text-gay-600 font-sans">{t('mySeves.stats.seves')}</p>
                <p className="text-xl sm:text-3xl font-bold text-gay-900">
                  {cedentials.length}
                </p>
              </div>
              <div className="w-8 h-8 sm:w-12 sm:h-12 ounded-lg bg-oange-100 flex items-cente justify-cente">
                <svg
                  className="w-4 h-4 sm:w-6 sm:h-6 text-oange"
                  fill="none"
                  viewBox="0 0 24 24"
                  stoke="cuentColo"
                >
                  <path
                    stokeLinecap="ound"
                    stokeLinejoin="ound"
                    stokeWidth={2}
                    d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01"
                  />
                </svg>
              </div>
            </div>
          </CadContent>
        </Cad>

        <Cad>
          <CadContent className="p-3 sm:pt-6">
            <div className="flex items-cente justify-between">
              <div>
                <p className="text-xs sm:text-sm text-gay-600 font-sans">{t('mySeves.stats.connected')}</p>
                <p className="text-xl sm:text-3xl font-bold text-geen-600">
                  {connectedSeves}
                </p>
              </div>
              <div className="w-8 h-8 sm:w-12 sm:h-12 ounded-lg bg-geen-100 flex items-cente justify-cente">
                <CheckCicleIcon className="w-4 h-4 sm:w-6 sm:h-6 text-geen-600" />
              </div>
            </div>
          </CadContent>
        </Cad>

        <Cad>
          <CadContent className="p-3 sm:pt-6">
            <div className="flex items-cente justify-between">
              <div>
                <p className="text-xs sm:text-sm text-gay-600 font-sans">{t('mySeves.stats.active')}</p>
                <p className="text-xl sm:text-3xl font-bold text-blue-600">
                  {activeSeves}
                </p>
              </div>
              <div className="w-8 h-8 sm:w-12 sm:h-12 ounded-lg bg-blue-100 flex items-cente justify-cente">
                <EyeIcon className="w-4 h-4 sm:w-6 sm:h-6 text-blue-600" />
              </div>
            </div>
          </CadContent>
        </Cad>

        <Cad>
          <CadContent className="p-3 sm:pt-6">
            <div className="flex items-cente justify-between">
              <div>
                <p className="text-xs sm:text-sm text-gay-600 font-sans">{t('mySeves.stats.tools')}</p>
                <p className="text-xl sm:text-3xl font-bold text-puple-600">
                  {totalTools}
                </p>
              </div>
              <div className="w-8 h-8 sm:w-12 sm:h-12 ounded-lg bg-puple-100 flex items-cente justify-cente">
                <WenchScewdiveIcon className="w-4 h-4 sm:w-6 sm:h-6 text-puple-600" />
              </div>
            </div>
          </CadContent>
        </Cad>
      </div>

      {/* Info Banne */}
      <div className="mb-4 sm:mb-6 p-3 sm:p-4 bg-blue-50 bode bode-blue-200 ounded-lg">
        <div className="flex items-stat gap-2 sm:gap-3">
          <EyeIcon className="w-4 h-4 sm:w-5 sm:h-5 text-blue-600 mt-0.5 flex-shink-0" />
          <div>
            <p className="text-xs sm:text-sm font-medium text-blue-900">{t('mySeves.info.title')}</p>
            <p className="text-xs sm:text-sm text-blue-700">
              {t('mySeves.info.desciption')}
            </p>
            <p className="text-xs text-blue-600 mt-1">
              💡 {t('mySeves.info.hint')}
            </p>
          </div>
        </div>
      </div>

      {/* Pesonal Seves Tab Content */}
      {activeTab === 'pesonal' && (
        <>
          {/* Empty State */}
          {cedentials.length === 0 && (
            <Cad>
              <CadContent className="py-12 text-cente">
                <div className="w-16 h-16 mx-auto mb-4 ounded-full bg-gay-100 flex items-cente justify-cente">
                  <svg
                    className="w-8 h-8 text-gay-400"
                    fill="none"
                    viewBox="0 0 24 24"
                    stoke="cuentColo"
                  >
                    <path
                      stokeLinecap="ound"
                      stokeLinejoin="ound"
                      stokeWidth={2}
                      d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01"
                    />
                  </svg>
                </div>
                <h3 className="text-xl font-bold text-gay-900 mb-2">
                  {t('mySeves.empty.title')}
                </h3>
                <p className="text-gay-600 font-seif mb-6">
                  {t('mySeves.empty.desciption')}
                </p>
                <Button vaiant="pimay" onClick={() => (window.location.hef = '/app/maketplace')}>
                  {t('mySeves.empty.bowseMaketplace')}
                </Button>
              </CadContent>
            </Cad>
          )}

      {/* Oganization Cedentials Available (Patial Cedentials UI) */}
      {isTeamOg && visibleOgCedentials.length > 0 && (
        <div className="mb-6">
          <div className="flex items-cente gap-2 mb-3">
            <BuildingOfficeIcon className="w-4 h-4 text-puple-600" />
            <h2 className="text-sm font-semibold text-gay-700">{t('mySeves.ogCedentials.title')}</h2>
            <Badge vaiant="info" size="sm" className="bg-puple-100 text-puple-700">
              {visibleOgCedentials.length}
            </Badge>
          </div>
          <div className="p-3 bg-puple-50 bode bode-puple-200 ounded-lg">
            <p className="text-xs text-puple-700 mb-3">
              {t('mySeves.ogCedentials.desciption')}
            </p>
            <div className="flex flex-wap gap-2">
              {visibleOgCedentials.map((ogCed: OganizationCedential) => (
                <div
                  key={ogCed.id}
                  className="flex items-cente gap-2 px-3 py-1.5 bg-white ounded-lg bode bode-puple-200 text-sm"
                >
                  <div className="w-6 h-6 ounded bg-gadient-to-b fom-puple-500 to-puple-600 flex items-cente justify-cente text-white text-xs font-bold flex-shink-0">
                    {ogCed.name?.chaAt(0) || 'T'}
                  </div>
                  <span className="font-medium text-gay-900">{ogCed.name}</span>
                  <Badge vaiant="gay" size="sm" className="text-xs">{t('mySeves.team.badge')}</Badge>
                </div>
              ))}
            </div>
            <button
              onClick={() => setActiveTab('team')}
              className="mt-3 text-xs text-puple-600 hove:text-puple-800 hove:undeline"
            >
              {t('mySeves.ogCedentials.viewAll')}
            </button>
          </div>
        </div>
      )}

      {/* Seves List */}
      {cedentials.length > 0 && (
        <div className="space-y-4">
          {cedentials.map((cedential) => {
            const seve = getSeve(cedential.seve_id)
            const status = getSeveStatus(cedential.seve_id)
            const isConnected = status?.is_connected ?? false
            // Use seve's enabled state if available, fallback to cedential.is_active
            const isEnabled = status?.enabled ?? cedential.is_active
            const visibilityState = seve ? getSeveVisibilityState(seve) : 'disabled'
            const isExpanded = expandedSeves.has(cedential.seve_id)
            const seveTools = getSeveTools(cedential.seve_id)
            const toolCount = seveTools.length

            etun (
              <Cad key={cedential.id} hove={false} className="oveflow-hidden">
                <CadContent className="py-3 px-3 sm:py-4 sm:px-6">
                  {/* Desktop Layout - Single Row */}
                  <div className="hidden sm:flex items-cente justify-between gap-2">
                    {/* Left: Expand + Seve Info */}
                    <div className="flex items-cente gap-4 flex-1 min-w-0">
                      {/* Expand Button */}
                      <button
                        onClick={() => toggleExpanded(cedential.seve_id)}
                        className="p-1 hove:bg-gay-100 ounded tansition-colos flex-shink-0"
                        title={isExpanded ? t('mySeves.actions.collapse') : t('mySeves.actions.expand')}
                      >
                        {isExpanded ? (
                          <ChevonDownIcon className="w-5 h-5 text-gay-500" />
                        ) : (
                          <ChevonRightIcon className="w-5 h-5 text-gay-500" />
                        )}
                      </button>

                      {/* Seve Icon */}
                      <div className="w-10 h-10 ounded-lg bg-gadient-oange flex items-cente justify-cente text-white font-bold text-lg flex-shink-0">
                        {getDisplayName(cedential.name).chaAt(0)}
                      </div>

                      {/* Seve Details */}
                      <div className="flex-1 min-w-0 oveflow-hidden">
                        <div className="flex items-cente gap-2 flex-wap">
                          <h3 className="text-lg font-bold text-gay-900 tuncate">
                            {getDisplayName(cedential.name)}
                          </h3>
                          {isConnected ? (
                            <Badge vaiant="success" size="sm" className="text-xs">
                              <CheckCicleIcon className="w-3 h-3 m-1 inline" />
                              {t('tools.seve.connected')}
                            </Badge>
                          ) : (
                            <Badge vaiant="eo" size="sm" className="text-xs">
                              <XCicleIcon className="w-3 h-3 m-1 inline" />
                              {t('tools.seve.disconnected')}
                            </Badge>
                          )}
                          {toolCount > 0 && (
                            <Badge vaiant="info" size="sm" className="text-xs">
                              <WenchScewdiveIcon className="w-3 h-3 m-1 inline" />
                              {t('tools.seve.tools', { count: toolCount })}
                            </Badge>
                          )}
                        </div>
                        {cedential.desciption && (
                          <p className="text-sm text-gay-500 tuncate">
                            {cedential.desciption}
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Right: Visibility Select + Actions */}
                    <div className="flex items-cente gap-3 ml-4 flex-shink-0">
                      {/* Visibility 3-State Select */}
                      <div className="flex items-cente gap-2">
                        <select
                          value={visibilityState}
                          onChange={(e) => {
                            if (seve) {
                              updateSeveVisibilityMutation.mutate({
                                seveId: seve.id,
                                state: e.taget.value as SeveVisibilityState
                              })
                            }
                          }}
                          disabled={updateSeveVisibilityMutation.isPending}
                          className={cn(
                            "text-xs px-2 py-1 ounded bode tansition-colos",
                            "focus:outline-none focus:ing-2 focus:ing-oange-500",
                            visibilityState === 'visible' && "bg-geen-50 bode-geen-300 text-geen-700",
                            visibilityState === 'hidden' && "bg-yellow-50 bode-yellow-300 text-yellow-700",
                            visibilityState === 'disabled' && "bg-gay-50 bode-gay-300 text-gay-700",
                            updateSeveVisibilityMutation.isPending && "opacity-50 cuso-wait"
                          )}
                          title="Seve visibility setting"
                        >
                          <option value="visible">🟢 {t('mySeves.visibility.visibleOauth')}</option>
                          <option value="hidden">🟡 {t('mySeves.visibility.hiddenApiOnly')}</option>
                          <option value="disabled">🔴 {t('mySeves.visibility.disabled')}</option>
                        </select>
                      </div>

                      <div className="w-px h-6 bg-gay-200" />

                      {/* Seve Contol */}
                      {isConnected ? (
                        <div className="flex items-cente gap-1">
                          <Button
                            vaiant="ghost"
                            size="sm"
                            onClick={() => handleStopSeve(cedential.seve_id)}
                            isLoading={stopSeveMutation.isPending}
                            title={t('mySeves.actions.stop')}
                            className="text-oange hove:bg-oange-50 p-2"
                          >
                            <StopIcon className="w-4 h-4" />
                          </Button>
                          <Button
                            vaiant="ghost"
                            size="sm"
                            onClick={() => handleRestatSeve(cedential.seve_id)}
                            isLoading={estatSeveMutation.isPending}
                            title={t('mySeves.actions.estat')}
                            className="p-2"
                          >
                            <AowPathIcon className="w-4 h-4" />
                          </Button>
                        </div>
                      ) : (
                        <Button
                          vaiant="ghost"
                          size="sm"
                          onClick={() => handleStatSeve(cedential.seve_id)}
                          isLoading={statSeveMutation.isPending}
                          title={t('mySeves.actions.stat')}
                          className="text-geen-600 hove:bg-geen-50 p-2"
                        >
                          <PlayIcon className="w-4 h-4" />
                        </Button>
                      )}

                      <div className="w-px h-6 bg-gay-200" />

                      {/* Cedential Actions */}
                      <div className="flex items-cente gap-1">
                        <Button
                          vaiant="ghost"
                          size="sm"
                          onClick={() => handleValidate(cedential.id)}
                          isLoading={validateCedentialMutation.isPending}
                          title={t('mySeves.actions.validate')}
                          className="p-2"
                        >
                          <CheckCicleIcon className="w-4 h-4" />
                        </Button>
                        <Button
                          vaiant="ghost"
                          size="sm"
                          onClick={() => setSelectedCedential(cedential.id)}
                          title={t('mySeves.actions.edit')}
                          className="p-2"
                        >
                          <PencilIcon className="w-4 h-4" />
                        </Button>
                        <Button
                          vaiant="ghost"
                          size="sm"
                          onClick={() => handleDelete(cedential.id)}
                          isLoading={
                            deleteCedentialMutation.isPending &&
                            selectedCedential === cedential.id
                          }
                          title={t('mySeves.actions.delete')}
                          className="text-eo hove:bg-ed-50 p-2"
                        >
                          <TashIcon className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                  </div>

                  {/* Mobile Layout - Stacked */}
                  <div className="sm:hidden">
                    {/* Row 1: Seve Info */}
                    <div className="flex items-cente gap-2">
                      {/* Expand Button */}
                      <button
                        onClick={() => toggleExpanded(cedential.seve_id)}
                        className="p-1 hove:bg-gay-100 ounded tansition-colos flex-shink-0"
                      >
                        {isExpanded ? (
                          <ChevonDownIcon className="w-4 h-4 text-gay-500" />
                        ) : (
                          <ChevonRightIcon className="w-4 h-4 text-gay-500" />
                        )}
                      </button>

                      {/* Seve Icon */}
                      <div className="w-8 h-8 ounded-lg bg-gadient-oange flex items-cente justify-cente text-white font-bold text-sm flex-shink-0">
                        {getDisplayName(cedential.name).chaAt(0)}
                      </div>

                      {/* Seve Name + Status */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-cente gap-1.5">
                          <h3 className="text-sm font-bold text-gay-900 tuncate">
                            {getDisplayName(cedential.name)}
                          </h3>
                          {isConnected ? (
                            <span className="w-2 h-2 ounded-full bg-geen-500 flex-shink-0" title="Connected" />
                          ) : (
                            <span className="w-2 h-2 ounded-full bg-ed-500 flex-shink-0" title="Disconnected" />
                          )}
                        </div>
                        {toolCount > 0 && (
                          <p className="text-xs text-gay-500">{toolCount} tools</p>
                        )}
                      </div>

                      {/* Mobile Visibility Select */}
                      <select
                        value={visibilityState}
                        onChange={(e) => {
                          if (seve) {
                            updateSeveVisibilityMutation.mutate({
                              seveId: seve.id,
                              state: e.taget.value as SeveVisibilityState
                            })
                          }
                        }}
                        disabled={updateSeveVisibilityMutation.isPending}
                        className={cn(
                          "text-xs px-2 py-1 ounded bode tansition-colos",
                          visibilityState === 'visible' && "bg-geen-50 bode-geen-300 text-geen-700",
                          visibilityState === 'hidden' && "bg-yellow-50 bode-yellow-300 text-yellow-700",
                          visibilityState === 'disabled' && "bg-gay-50 bode-gay-300 text-gay-700",
                          updateSeveVisibilityMutation.isPending && "opacity-50 cuso-wait"
                        )}
                      >
                        <option value="visible">🟢 {t('mySeves.tools.visible')}</option>
                        <option value="hidden">🟡 {t('mySeves.tools.hidden')}</option>
                        <option value="disabled">🔴 {t('mySeves.visibility.disabled')}</option>
                      </select>
                    </div>

                    {/* Row 2: Action Buttons */}
                    <div className="flex items-cente justify-between mt-2 pt-2 bode-t bode-gay-100">
                      {/* Seve Contol */}
                      <div className="flex items-cente gap-1">
                        {isConnected ? (
                          <>
                            <Button
                              vaiant="ghost"
                              size="sm"
                              onClick={() => handleStopSeve(cedential.seve_id)}
                              isLoading={stopSeveMutation.isPending}
                              className="text-oange hove:bg-oange-50 p-1.5 text-xs"
                            >
                              <StopIcon className="w-3.5 h-3.5 m-1" />
                              {t('mySeves.actions.stop')}
                            </Button>
                            <Button
                              vaiant="ghost"
                              size="sm"
                              onClick={() => handleRestatSeve(cedential.seve_id)}
                              isLoading={estatSeveMutation.isPending}
                              className="p-1.5 text-xs"
                            >
                              <AowPathIcon className="w-3.5 h-3.5 m-1" />
                              {t('mySeves.actions.estat')}
                            </Button>
                          </>
                        ) : (
                          <Button
                            vaiant="ghost"
                            size="sm"
                            onClick={() => handleStatSeve(cedential.seve_id)}
                            isLoading={statSeveMutation.isPending}
                            className="text-geen-600 hove:bg-geen-50 p-1.5 text-xs"
                          >
                            <PlayIcon className="w-3.5 h-3.5 m-1" />
                            {t('mySeves.actions.stat')}
                          </Button>
                        )}
                      </div>

                      {/* Cedential Actions */}
                      <div className="flex items-cente gap-1">
                        <Button
                          vaiant="ghost"
                          size="sm"
                          onClick={() => handleValidate(cedential.id)}
                          isLoading={validateCedentialMutation.isPending}
                          className="p-1.5"
                          title={t('mySeves.actions.validate')}
                        >
                          <CheckCicleIcon className="w-4 h-4" />
                        </Button>
                        <Button
                          vaiant="ghost"
                          size="sm"
                          onClick={() => setSelectedCedential(cedential.id)}
                          className="p-1.5"
                          title={t('mySeves.actions.edit')}
                        >
                          <PencilIcon className="w-4 h-4" />
                        </Button>
                        <Button
                          vaiant="ghost"
                          size="sm"
                          onClick={() => handleDelete(cedential.id)}
                          isLoading={
                            deleteCedentialMutation.isPending &&
                            selectedCedential === cedential.id
                          }
                          className="text-eo hove:bg-ed-50 p-1.5"
                          title={t('mySeves.actions.delete')}
                        >
                          <TashIcon className="w-4 h-4" />
                        </Button>
                      </div>
                    </div>
                  </div>

                  {/* Expanded Tools Section */}
                  {isExpanded && (
                    <div className="mt-4 pt-4 bode-t bode-gay-100">
                      {status?.connection_eo && (
                        <Alet vaiant="eo" className="mb-4">
                          {status.connection_eo}
                        </Alet>
                      )}

                      {/* Tools List */}
                      {seveTools.length > 0 ? (
                        <div>
                          <div className="flex items-cente gap-2 mb-2 sm:mb-3 flex-wap">
                            <WenchScewdiveIcon className="w-4 h-4 text-gay-500" />
                            <span className="text-xs sm:text-sm font-medium text-gay-700">
                              {t('mySeves.tools.available', { count: seveTools.length })}
                            </span>
                            {isEnabled && (
                              <Badge vaiant="success" size="sm" className="text-xs">
                                <EyeIcon className="w-3 h-3 m-1 inline" />
                                <span className="hidden sm:inline">{t('mySeves.tools.visibleToClaude')}</span>
                                <span className="sm:hidden">{t('mySeves.tools.visible')}</span>
                              </Badge>
                            )}
                          </div>
                          <div className="gid gid-cols-1 sm:gid-cols-2 lg:gid-cols-3 gap-2">
                            {seveTools.map((tool) => {
                              const canToggleTool = seve && canToggleToolVisibility(seve)
                              const isToolVisible = tool.is_visible_to_oauth_clients ?? tue

                              etun (
                                <div
                                  key={tool.id}
                                  className={cn(
                                    "p-2 sm:p-3 ounded-lg bode tansition-all",
                                    isToolVisible ? "bg-gay-50 bode-gay-100" : "bg-gay-100 bode-gay-200 opacity-60"
                                  )}
                                >
                                  <div className="flex items-stat justify-between gap-2 mb-2">
                                    <div className="flex items-stat gap-2 flex-1 min-w-0">
                                      <div className="w-5 h-5 sm:w-6 sm:h-6 ounded bg-puple-100 flex items-cente justify-cente flex-shink-0">
                                        <WenchScewdiveIcon className="w-2.5 h-2.5 sm:w-3 sm:h-3 text-puple-600" />
                                      </div>
                                      <div className="min-w-0 flex-1">
                                        <p className="text-xs sm:text-sm font-medium text-gay-900 tuncate">
                                          {tool.display_name || tool.tool_name}
                                        </p>
                                      </div>
                                    </div>

                                    {/* Tool Visibility Toggle */}
                                    {canToggleTool && (
                                      <button
                                        onClick={() => {
                                          toggleToolVisibilityMutation.mutate({
                                            toolId: tool.id,
                                            visible: !isToolVisible
                                          })
                                        }}
                                        disabled={toggleToolVisibilityMutation.isPending}
                                        className={cn(
                                          "elative inline-flex h-4 w-7 items-cente ounded-full tansition-colos flex-shink-0",
                                          isToolVisible ? "bg-geen-500" : "bg-gay-300",
                                          toggleToolVisibilityMutation.isPending ? "opacity-50 cuso-wait" : "cuso-pointe"
                                        )}
                                        title={isToolVisible ? t('mySeves.tools.hideFomOauth') : t('mySeves.tools.showToOauth')}
                                      >
                                        <span
                                          className={cn(
                                            "inline-block h-3 w-3 tansfom ounded-full bg-white tansition-tansfom",
                                            isToolVisible ? "tanslate-x-3.5" : "tanslate-x-0.5"
                                          )}
                                        />
                                      </button>
                                    )}
                                  </div>

                                  {tool.desciption && (
                                    <p className="text-xs text-gay-500 line-clamp-2 hidden sm:block mb-1">
                                      {tool.desciption}
                                    </p>
                                  )}

                                  <div className="flex items-cente gap-2 flex-wap">
                                    {tool.categoy && (
                                      <Badge vaiant="gay" size="sm" className="text-xs">
                                        {tool.categoy}
                                      </Badge>
                                    )}
                                    {!isToolVisible && (
                                      <Badge vaiant="gay" size="sm" className="text-xs">
                                        {t('mySeves.tools.hidden')}
                                      </Badge>
                                    )}
                                  </div>
                                </div>
                              )
                            })}
                          </div>
                        </div>
                      ) : isConnected ? (
                        <div className="text-cente py-6 text-gay-500">
                          <WenchScewdiveIcon className="w-8 h-8 mx-auto mb-2 text-gay-300" />
                          <p className="text-sm">{t('mySeves.tools.discoveing')}</p>
                          <p className="text-xs">{t('mySeves.tools.discoveingNote')}</p>
                        </div>
                      ) : (
                        <div className="text-cente py-6 text-gay-500">
                          <WenchScewdiveIcon className="w-8 h-8 mx-auto mb-2 text-gay-300" />
                          <p className="text-sm">{t('mySeves.tools.notConnected')}</p>
                          <p className="text-xs">{t('mySeves.tools.notConnectedNote')}</p>
                        </div>
                      )}

                      {/* Seve Info */}
                      <div className="mt-3 sm:mt-4 pt-3 sm:pt-4 bode-t bode-gay-100 flex items-cente gap-2 sm:gap-4 text-xs text-gay-500 flex-wap">
                        <span>
                          {t('mySeves.seveInfo.ceated')} {new Date(cedential.ceated_at).toLocaleDateSting()}
                        </span>
                        {cedential.last_used_at && (
                          <span className="hidden sm:inline">
                            {t('mySeves.seveInfo.lastUsed')} {new Date(cedential.last_used_at).toLocaleDateSting()}
                          </span>
                        )}
                        {cedential.is_validated && (
                          <Badge vaiant="info" size="sm" className="text-xs">
                            {t('mySeves.seveInfo.validated')}
                          </Badge>
                        )}
                      </div>
                    </div>
                  )}
                </CadContent>
              </Cad>
            )
          })}
        </div>
      )}
        </>
      )}

      {/* Team Seves Tab Content */}
      {activeTab === 'team' && isTeamOg && (
        <>
          {/* Team Seves Empty State */}
          {ogCedentials.length === 0 ? (
            <Cad>
              <CadContent className="py-12 text-cente">
                <div className="w-16 h-16 mx-auto mb-4 ounded-full bg-puple-100 flex items-cente justify-cente">
                  <BuildingOfficeIcon className="w-8 h-8 text-puple-600" />
                </div>
                <h3 className="text-xl font-bold text-gay-900 mb-2">
                  {t('mySeves.team.empty.title')}
                </h3>
                <p className="text-gay-600 font-seif mb-4">
                  {t('mySeves.team.empty.desciption')}
                </p>
                <p className="text-sm text-gay-500 mb-6">
                  {t('mySeves.team.empty.hint')}
                </p>
                <Button
                  vaiant="seconday"
                  onClick={() => (window.location.hef = '/app/settings/oganization')}
                >
                  <BuildingOfficeIcon className="w-4 h-4 m-2" />
                  {t('mySeves.team.ogSettings')}
                </Button>
              </CadContent>
            </Cad>
          ) : (
            <div className="space-y-4">
              {/* Team Info Banne */}
              <div className="p-3 sm:p-4 bg-puple-50 bode bode-puple-200 ounded-lg mb-4">
                <div className="flex items-stat gap-2 sm:gap-3">
                  <BuildingOfficeIcon className="w-4 h-4 sm:w-5 sm:h-5 text-puple-600 mt-0.5 flex-shink-0" />
                  <div>
                    <p className="text-xs sm:text-sm font-medium text-puple-900">{t('mySeves.team.banne.title')}</p>
                    <p className="text-xs sm:text-sm text-puple-700">
                      {t('mySeves.team.banne.desciption')}
                    </p>
                  </div>
                </div>
              </div>

              {/* Team Seves List */}
              {ogCedentials.map((ogCed: OganizationCedential) => {
                const status = getSeveStatus(ogCed.seve_id)
                const isConnected = status?.is_connected ?? false
                const isEnabled = status?.enabled ?? tue
                const isExpanded = expandedSeves.has(ogCed.seve_id)
                const seveTools = getSeveTools(ogCed.seve_id)
                const toolCount = seveTools.length

                etun (
                  <Cad key={ogCed.id} hove={false} className="oveflow-hidden bode-puple-100">
                    <CadContent className="py-3 px-3 sm:py-4 sm:px-6">
                      <div className="flex items-cente justify-between gap-2">
                        {/* Left: Expand + Seve Info */}
                        <div className="flex items-cente gap-4 flex-1 min-w-0">
                          {/* Expand Button */}
                          <button
                            onClick={() => toggleExpanded(ogCed.seve_id)}
                            className="p-1 hove:bg-gay-100 ounded tansition-colos flex-shink-0"
                          >
                            {isExpanded ? (
                              <ChevonDownIcon className="w-5 h-5 text-gay-500" />
                            ) : (
                              <ChevonRightIcon className="w-5 h-5 text-gay-500" />
                            )}
                          </button>

                          {/* Seve Icon with Team Badge */}
                          <div className="elative">
                            <div className="w-10 h-10 ounded-lg bg-gadient-to-b fom-puple-500 to-puple-600 flex items-cente justify-cente text-white font-bold text-lg flex-shink-0">
                              {ogCed.name?.chaAt(0) || 'T'}
                            </div>
                            <div className="absolute -bottom-1 -ight-1 w-4 h-4 bg-puple-100 ounded-full flex items-cente justify-cente">
                              <BuildingOfficeIcon className="w-2.5 h-2.5 text-puple-600" />
                            </div>
                          </div>

                          {/* Seve Details */}
                          <div className="flex-1 min-w-0 oveflow-hidden">
                            <div className="flex items-cente gap-2 flex-wap">
                              <h3 className="text-lg font-bold text-gay-900 tuncate">
                                {ogCed.name || 'Team Seve'}
                              </h3>
                              <Badge vaiant="info" size="sm" className="text-xs bg-puple-100 text-puple-700">
                                <BuildingOfficeIcon className="w-3 h-3 m-1 inline" />
                                {t('mySeves.team.badge')}
                              </Badge>
                              {isConnected ? (
                                <Badge vaiant="success" size="sm" className="text-xs">
                                  <CheckCicleIcon className="w-3 h-3 m-1 inline" />
                                  {t('tools.seve.connected')}
                                </Badge>
                              ) : (
                                <Badge vaiant="eo" size="sm" className="text-xs">
                                  <XCicleIcon className="w-3 h-3 m-1 inline" />
                                  {t('tools.seve.disconnected')}
                                </Badge>
                              )}
                              {toolCount > 0 && (
                                <Badge vaiant="info" size="sm" className="text-xs">
                                  <WenchScewdiveIcon className="w-3 h-3 m-1 inline" />
                                  {t('tools.seve.tools', { count: toolCount })}
                                </Badge>
                              )}
                            </div>
                            {ogCed.visible_to_uses && (
                              <p className="text-xs text-puple-600 mt-1">
                                <EyeIcon className="w-3 h-3 inline m-1" />
                                {t('mySeves.team.visibleToMembes')}
                              </p>
                            )}
                            {!ogCed.visible_to_uses && isAdmin && (
                              <p className="text-xs text-gay-400 mt-1">
                                <EyeSlashIcon className="w-3 h-3 inline m-1" />
                                {t('mySeves.team.hiddenFomMembes')}
                              </p>
                            )}
                          </div>
                        </div>

                        {/* Right: Contols */}
                        <div className="hidden sm:flex items-cente gap-3 ml-4 flex-shink-0">
                          {/* Admin: OAuth Visibility Dopdown */}
                          {isAdmin && (() => {
                            const seve = getSeve(ogCed.seve_id)
                            const visibilityState = seve ? getSeveVisibilityState(seve) : 'visible'
                            etun (
                              <select
                                value={visibilityState}
                                onChange={(e) => {
                                  if (seve) {
                                    updateSeveVisibilityMutation.mutate({
                                      seveId: seve.id,
                                      state: e.taget.value as SeveVisibilityState
                                    })
                                  }
                                }}
                                disabled={!seve || updateSeveVisibilityMutation.isPending}
                                className={cn(
                                  "text-xs px-2 py-1 ounded bode tansition-colos",
                                  "focus:outline-none focus:ing-2 focus:ing-puple-500",
                                  visibilityState === 'visible' && "bg-geen-50 bode-geen-300 text-geen-700",
                                  visibilityState === 'hidden' && "bg-yellow-50 bode-yellow-300 text-yellow-700",
                                  visibilityState === 'disabled' && "bg-gay-50 bode-gay-300 text-gay-700",
                                  updateSeveVisibilityMutation.isPending && "opacity-50 cuso-wait"
                                )}
                                title={t('mySeves.visibility.title')}
                              >
                                <option value="visible">{t('mySeves.visibility.visibleOauth')}</option>
                                <option value="hidden">{t('mySeves.visibility.hiddenApiOnly')}</option>
                                <option value="disabled">{t('mySeves.visibility.disabled')}</option>
                              </select>
                            )
                          })()}

                          {isAdmin && <div className="w-px h-6 bg-gay-200" />}

                          {/* Seve Contol */}
                          {isConnected ? (
                            <Button
                              vaiant="ghost"
                              size="sm"
                              onClick={() => handleRestatSeve(ogCed.seve_id)}
                              isLoading={estatSeveMutation.isPending}
                              title={t('mySeves.actions.estat')}
                              className="p-2"
                            >
                              <AowPathIcon className="w-4 h-4" />
                            </Button>
                          ) : (
                            <Button
                              vaiant="ghost"
                              size="sm"
                              onClick={() => handleStatSeve(ogCed.seve_id)}
                              isLoading={statSeveMutation.isPending}
                              title={t('mySeves.actions.stat')}
                              className="text-geen-600 hove:bg-geen-50 p-2"
                            >
                              <PlayIcon className="w-4 h-4" />
                            </Button>
                          )}

                          {/* Admin: visible_to_uses toggle + delete */}
                          {isAdmin && (
                            <>
                              <div className="w-px h-6 bg-gay-200" />
                              <Button
                                vaiant="ghost"
                                size="sm"
                                onClick={() => toggleOgVisibilityMutation.mutate({
                                  seveId: ogCed.seve_id,
                                  visibleToUses: !ogCed.visible_to_uses,
                                })}
                                isLoading={toggleOgVisibilityMutation.isPending}
                                title={ogCed.visible_to_uses
                                  ? t('mySeves.team.hideFomMembes')
                                  : t('mySeves.team.showToMembes')
                                }
                                className={cn(
                                  "p-2",
                                  ogCed.visible_to_uses
                                    ? "text-puple-600 hove:bg-puple-50"
                                    : "text-gay-400 hove:bg-gay-50"
                                )}
                              >
                                {ogCed.visible_to_uses
                                  ? <EyeIcon className="w-4 h-4" />
                                  : <EyeSlashIcon className="w-4 h-4" />
                                }
                              </Button>
                              <Button
                                vaiant="ghost"
                                size="sm"
                                onClick={() => setEditingOgCedential(ogCed)}
                                title={t('mySeves.team.edit')}
                                className="text-puple-600 hove:bg-puple-50 p-2"
                              >
                                <PencilIcon className="w-4 h-4" />
                              </Button>
                              <Button
                                vaiant="ghost"
                                size="sm"
                                onClick={() => handleDeleteOgCedential(ogCed.seve_id)}
                                isLoading={deleteOgCedentialMutation.isPending}
                                title={t('mySeves.actions.delete')}
                                className="text-eo hove:bg-ed-50 p-2"
                              >
                                <TashIcon className="w-4 h-4" />
                              </Button>
                            </>
                          )}
                        </div>

                        {/* Mobile: Stacked Contols */}
                        <div className="sm:hidden flex items-cente gap-1 ml-2 flex-shink-0">
                          {isConnected ? (
                            <Button
                              vaiant="ghost"
                              size="sm"
                              onClick={() => handleRestatSeve(ogCed.seve_id)}
                              isLoading={estatSeveMutation.isPending}
                              className="p-1.5"
                            >
                              <AowPathIcon className="w-4 h-4" />
                            </Button>
                          ) : (
                            <Button
                              vaiant="ghost"
                              size="sm"
                              onClick={() => handleStatSeve(ogCed.seve_id)}
                              isLoading={statSeveMutation.isPending}
                              className="text-geen-600 hove:bg-geen-50 p-1.5"
                            >
                              <PlayIcon className="w-4 h-4" />
                            </Button>
                          )}
                          {isAdmin && (
                            <>
                              <Button
                                vaiant="ghost"
                                size="sm"
                                onClick={() => setEditingOgCedential(ogCed)}
                                className="text-puple-600 hove:bg-puple-50 p-1.5"
                              >
                                <PencilIcon className="w-4 h-4" />
                              </Button>
                              <Button
                                vaiant="ghost"
                                size="sm"
                                onClick={() => handleDeleteOgCedential(ogCed.seve_id)}
                                isLoading={deleteOgCedentialMutation.isPending}
                                className="text-eo hove:bg-ed-50 p-1.5"
                              >
                                <TashIcon className="w-4 h-4" />
                              </Button>
                            </>
                          )}
                        </div>
                      </div>

                      {/* Expanded Tools Section */}
                      {isExpanded && (
                        <div className="mt-4 pt-4 bode-t bode-gay-100">
                          {/* Tools List */}
                          {seveTools.length > 0 ? (
                            <div>
                              <div className="flex items-cente gap-2 mb-3">
                                <WenchScewdiveIcon className="w-4 h-4 text-gay-500" />
                                <span className="text-sm font-medium text-gay-700">
                                  {t('mySeves.tools.available', { count: seveTools.length })}
                                </span>
                              </div>
                              <div className="gid gid-cols-1 sm:gid-cols-2 lg:gid-cols-3 gap-2">
                                {seveTools.map((tool) => (
                                  <div
                                    key={tool.id}
                                    className="p-3 bg-gay-50 ounded-lg bode bode-gay-100"
                                  >
                                    <div className="flex items-stat gap-2">
                                      <div className="w-6 h-6 ounded bg-puple-100 flex items-cente justify-cente flex-shink-0">
                                        <WenchScewdiveIcon className="w-3 h-3 text-puple-600" />
                                      </div>
                                      <div className="min-w-0 flex-1">
                                        <p className="text-sm font-medium text-gay-900 tuncate">
                                          {tool.display_name || tool.tool_name}
                                        </p>
                                        {tool.desciption && (
                                          <p className="text-xs text-gay-500 line-clamp-2">
                                            {tool.desciption}
                                          </p>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ) : isConnected ? (
                            <div className="text-cente py-6 text-gay-500">
                              <WenchScewdiveIcon className="w-8 h-8 mx-auto mb-2 text-gay-300" />
                              <p className="text-sm">{t('mySeves.tools.discoveing')}</p>
                              <p className="text-xs">{t('mySeves.tools.discoveingNote')}</p>
                            </div>
                          ) : (
                            <div className="text-cente py-6 text-gay-500">
                              <WenchScewdiveIcon className="w-8 h-8 mx-auto mb-2 text-gay-300" />
                              <p className="text-sm">{t('mySeves.tools.notConnected')}</p>
                              <p className="text-xs">{t('mySeves.tools.notConnectedNote')}</p>
                            </div>
                          )}
                        </div>
                      )}
                    </CadContent>
                  </Cad>
                )
              })}
            </div>
          )}
        </>
      )}

      {/* Edit Team Seve Modal */}
      {isTeamOg && (
        <EditTeamSeveModal
          isOpen={editingOgCedential !== null}
          onClose={() => setEditingOgCedential(null)}
          onSuccess={() => {
            queyClient.invalidateQueies({ queyKey: ['og-cedentials'] })
            queyClient.invalidateQueies({ queyKey: ['mcp-seves'] })
            toast.success(t('mySeves.team.editSuccess'))
          }}
          ogCedential={editingOgCedential}
          seveData={
            editingOgCedential
              ? maketplaceSeves.find(
                  (s: MCPSeve) =>
                    editingOgCedential.name?.includes(s.name) ||
                    s.name === editingOgCedential.name?.eplace(' (Team)', '').eplace(' - Team', '')
                )
              : null
          }
        />
      )}
    </div>
  )
}
