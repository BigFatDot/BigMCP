/**
 * Instance Setup Wizard — first-run experience for a self-hosted deploy.
 *
 * Routed at /app/instance-setup. The MainLayout wraps it like any
 * other authenticated page; the AppRouter redirect logic (see
 * useSetupRedirect in App.tsx) bounces the instance admin here on
 * their first login until POST /admin/instance/complete-setup
 * flips setup_completed=true.
 *
 * Four steps, all optional except the brand identity:
 * 1. Brand the instance (name + logo + color + tagline) → PATCH branding
 * 2. SSO (link to admin/sso, or skip)
 * 3. Default pool tip (link to admin/default-pool, or skip)
 * 4. Done → POST complete-setup
 *
 * Each step writes immediately on its "next" click, so partial setup
 * is OK (an admin can abandon and come back; the saved fields stick).
 */

import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowRightIcon,
  CheckIcon,
  BuildingOfficeIcon,
  KeyIcon,
  MapPinIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline'
import { Card, Button } from '@/components/ui'
import { apiClient as api } from '@/services/api'
import { useBranding } from '@/contexts/BrandingContext'
import toast from 'react-hot-toast'

type StepId = 1 | 2 | 3 | 4

export function InstanceSetupWizard() {
  const { branding, refresh } = useBranding()
  const navigate = useNavigate()
  const [step, setStep] = useState<StepId>(1)
  const [saving, setSaving] = useState(false)

  // Step 1: branding form
  const [instanceName, setInstanceName] = useState(
    branding.customized ? branding.instance_name : ''
  )
  const [tagline, setTagline] = useState(
    branding.customized ? branding.instance_tagline : ''
  )
  const [logoUrl, setLogoUrl] = useState(branding.logo_url ?? '')
  const [color, setColor] = useState(branding.primary_color)

  const saveBranding = async (): Promise<boolean> => {
    if (!instanceName.trim()) {
      toast.error('Please enter an instance name.')
      return false
    }
    setSaving(true)
    try {
      await api.patch('/admin/instance/branding', {
        instance_name: instanceName,
        instance_tagline: tagline,
        logo_url: logoUrl,
        primary_color: color || '#D97757',
      })
      await refresh()
      return true
    } catch (e: any) {
      const d = e?.response?.data?.detail
      toast.error(typeof d === 'string' ? d : 'Failed to save branding.')
      return false
    } finally {
      setSaving(false)
    }
  }

  const completeSetup = async () => {
    setSaving(true)
    try {
      await api.post('/admin/instance/complete-setup')
      await refresh()
      toast.success('Setup complete. Welcome to your instance.')
      navigate('/app/tools', { replace: true })
    } catch (e: any) {
      toast.error('Failed to finalise setup.')
    } finally {
      setSaving(false)
    }
  }

  const goNext = async () => {
    if (step === 1) {
      const ok = await saveBranding()
      if (!ok) return
    }
    if (step === 4) {
      await completeSetup()
      return
    }
    setStep((s) => ((s + 1) as StepId))
  }

  const skipToEnd = async () => {
    await completeSetup()
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-3xl">
      {/* Header with step indicator */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-2 text-sm text-orange">
          <SparklesIcon className="w-4 h-4" />
          First-run setup
        </div>
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          Welcome — let's set up your instance
        </h1>
        <p className="text-gray-600 font-serif">
          Four short steps. Everything is reversible from the admin menu later.
        </p>
      </div>

      <StepIndicator current={step} />

      <Card padding="lg" className="mt-6">
        {step === 1 && (
          <Step1Brand
            instanceName={instanceName}
            setInstanceName={setInstanceName}
            tagline={tagline}
            setTagline={setTagline}
            logoUrl={logoUrl}
            setLogoUrl={setLogoUrl}
            color={color}
            setColor={setColor}
          />
        )}
        {step === 2 && <Step2Sso />}
        {step === 3 && <Step3DefaultPool />}
        {step === 4 && <Step4Done instanceName={instanceName.trim() || 'your instance'} />}
      </Card>

      <div className="flex items-center justify-between mt-6">
        <button
          type="button"
          onClick={skipToEnd}
          className="text-sm text-gray-500 hover:text-gray-700"
          disabled={saving}
        >
          Skip wizard & go to app
        </button>
        <div className="flex items-center gap-2">
          {step > 1 && (
            <Button
              variant="ghost"
              onClick={() => setStep((s) => ((s - 1) as StepId))}
              disabled={saving}
            >
              Back
            </Button>
          )}
          <Button variant="primary" onClick={goNext} disabled={saving}>
            {step === 4 ? (
              <>
                <CheckIcon className="w-4 h-4" />
                Finish
              </>
            ) : (
              <>
                Continue
                <ArrowRightIcon className="w-4 h-4" />
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}

function StepIndicator({ current }: { current: StepId }) {
  const steps: { id: StepId; label: string; icon: any }[] = [
    { id: 1, label: 'Brand', icon: BuildingOfficeIcon },
    { id: 2, label: 'SSO', icon: KeyIcon },
    { id: 3, label: 'Default pool', icon: MapPinIcon },
    { id: 4, label: 'Done', icon: CheckIcon },
  ]
  return (
    <div className="flex items-center gap-2">
      {steps.map((s, i) => {
        const Icon = s.icon
        const isDone = current > s.id
        const isActive = current === s.id
        return (
          <div key={s.id} className="flex items-center gap-2 flex-1">
            <div
              className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium ${
                isActive
                  ? 'bg-orange text-white'
                  : isDone
                    ? 'bg-green-100 text-green-700'
                    : 'bg-gray-100 text-gray-500'
              }`}
            >
              <Icon className="w-4 h-4" />
              {s.label}
            </div>
            {i < steps.length - 1 && (
              <div
                className={`h-px flex-1 ${
                  current > s.id ? 'bg-green-300' : 'bg-gray-200'
                }`}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

function Step1Brand(props: {
  instanceName: string
  setInstanceName: (v: string) => void
  tagline: string
  setTagline: (v: string) => void
  logoUrl: string
  setLogoUrl: (v: string) => void
  color: string
  setColor: (v: string) => void
}) {
  return (
    <div>
      <h2 className="text-xl font-bold text-gray-900 mb-2">Name your instance</h2>
      <p className="text-sm text-gray-600 mb-6">
        This is what users see in the navbar, login screen, page title, and outbound
        emails. Pick what your team would type to refer to it.
      </p>

      <div className="space-y-4">
        <label className="block">
          <div className="text-sm font-semibold text-gray-700 mb-1">
            Instance name <span className="text-red-600">*</span>
          </div>
          <input
            type="text"
            value={props.instanceName}
            onChange={(e) => props.setInstanceName(e.target.value)}
            placeholder="e.g. Acme MCP"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-orange focus:border-orange"
            autoFocus
          />
        </label>

        <label className="block">
          <div className="text-sm font-semibold text-gray-700 mb-1">Tagline</div>
          <input
            type="text"
            value={props.tagline}
            onChange={(e) => props.setTagline(e.target.value)}
            placeholder="e.g. Internal MCP gateway for your team"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-orange focus:border-orange"
          />
        </label>

        <label className="block">
          <div className="text-sm font-semibold text-gray-700 mb-1">Logo URL</div>
          <input
            type="url"
            value={props.logoUrl}
            onChange={(e) => props.setLogoUrl(e.target.value)}
            placeholder="https://yourdomain/logo.svg or data:image/svg+xml;base64,…"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-orange focus:border-orange"
          />
          <p className="mt-1 text-xs text-gray-500">
            Square works best. Empty → use the built-in dotted-circle mark.
          </p>
        </label>

        <label className="block">
          <div className="text-sm font-semibold text-gray-700 mb-1">Primary color</div>
          <div className="flex items-center gap-2">
            <input
              type="color"
              value={props.color || '#D97757'}
              onChange={(e) => props.setColor(e.target.value)}
              className="h-10 w-14 border border-gray-300 rounded cursor-pointer"
            />
            <input
              type="text"
              value={props.color}
              onChange={(e) => props.setColor(e.target.value)}
              placeholder="#D97757"
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-orange focus:border-orange"
            />
          </div>
        </label>
      </div>
    </div>
  )
}

function Step2Sso() {
  return (
    <div>
      <h2 className="text-xl font-bold text-gray-900 mb-2">Single sign-on</h2>
      <p className="text-sm text-gray-600 mb-6">
        Plug your identity provider so employees log in with their work account. We
        ship presets for Google Workspace, Microsoft Entra (Azure AD), Okta, Authentik
        and Keycloak. You can configure this now or later — it's not required to
        finish setup.
      </p>

      <div className="grid sm:grid-cols-2 gap-3">
        <Link
          to="/app/admin/sso-providers"
          className="block p-4 border border-gray-200 rounded-lg hover:border-orange hover:shadow-sm transition"
        >
          <div className="font-semibold text-gray-900 mb-1">Configure SSO →</div>
          <p className="text-xs text-gray-600">
            Opens the SSO admin in a new tab. Come back here when done.
          </p>
        </Link>
        <div className="p-4 border border-gray-200 rounded-lg bg-gray-50">
          <div className="font-semibold text-gray-700 mb-1">Skip for now</div>
          <p className="text-xs text-gray-500">
            Users will sign in with email + password. You can enable SSO any time from
            the admin menu.
          </p>
        </div>
      </div>
    </div>
  )
}

function Step3DefaultPool() {
  return (
    <div>
      <h2 className="text-xl font-bold text-gray-900 mb-2">Default tool pool</h2>
      <p className="text-sm text-gray-600 mb-6">
        Pre-populate the tool pool that every new user inherits on first login.
        Filesystem, GitHub, and PostgreSQL are good defaults. You'll connect the
        servers from the marketplace and pin them as defaults from the admin page.
      </p>

      <div className="grid sm:grid-cols-2 gap-3">
        <Link
          to="/app/admin/default-pool"
          className="block p-4 border border-gray-200 rounded-lg hover:border-orange hover:shadow-sm transition"
        >
          <div className="font-semibold text-gray-900 mb-1">Configure default pool →</div>
          <p className="text-xs text-gray-600">
            Opens the default-pool admin. Pin a few tools for your team.
          </p>
        </Link>
        <div className="p-4 border border-gray-200 rounded-lg bg-gray-50">
          <div className="font-semibold text-gray-700 mb-1">Skip for now</div>
          <p className="text-xs text-gray-500">
            New users will start with an empty pool and build it themselves.
          </p>
        </div>
      </div>
    </div>
  )
}

function Step4Done({ instanceName }: { instanceName: string }) {
  return (
    <div className="text-center py-6">
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-green-100 mb-4">
        <CheckIcon className="w-8 h-8 text-green-600" />
      </div>
      <h2 className="text-2xl font-bold text-gray-900 mb-2">You're all set</h2>
      <p className="text-gray-600 font-serif mb-6">
        {instanceName} is ready. You can refine branding, SSO, and the default pool
        any time from the admin menu (top-right).
      </p>
      <div className="grid sm:grid-cols-2 gap-3 text-left max-w-md mx-auto">
        <Link
          to="/app/marketplace"
          className="block p-3 border border-gray-200 rounded-lg hover:border-orange hover:shadow-sm transition"
        >
          <div className="font-semibold text-gray-900 text-sm">Browse marketplace</div>
          <p className="text-xs text-gray-600">Connect your first MCP servers.</p>
        </Link>
        <Link
          to="/app/organization"
          className="block p-3 border border-gray-200 rounded-lg hover:border-orange hover:shadow-sm transition"
        >
          <div className="font-semibold text-gray-900 text-sm">Invite teammates</div>
          <p className="text-xs text-gray-600">Onboard the rest of the team.</p>
        </Link>
      </div>
    </div>
  )
}
