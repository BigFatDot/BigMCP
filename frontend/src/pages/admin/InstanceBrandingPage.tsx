/**
 * Instance Branding — white-label this BigMCP deploy.
 *
 * Lets the instance admin override name, tagline, logo URL, favicon,
 * primary color, support email, instance URL, and legal entity. Sends
 * a partial PATCH so empty fields fall back to env-var / built-in
 * defaults. Live preview on the right mirrors what the navbar /
 * login screen will look like.
 *
 * "Reset to defaults" sends an empty payload for each field which the
 * backend interprets as "clear this column".
 */

import { useEffect, useMemo, useState } from 'react'
import { ArrowPathIcon, BuildingOfficeIcon, CheckCircleIcon } from '@heroicons/react/24/outline'
import { Card, Button, Badge } from '@/components/ui'
import { apiClient as api } from '@/services/api'
import { useBranding, type Branding } from '@/contexts/BrandingContext'
import toast from 'react-hot-toast'

type FormState = {
  instance_name: string
  instance_tagline: string
  logo_url: string
  favicon_url: string
  primary_color: string
  support_email: string
  instance_url: string
  legal_entity: string
  welcome_message: string
}

function toForm(b: Branding): FormState {
  return {
    instance_name: b.customized ? b.instance_name : '',
    instance_tagline: b.customized ? b.instance_tagline : '',
    logo_url: b.logo_url ?? '',
    favicon_url: b.favicon_url ?? '',
    primary_color: b.primary_color,
    support_email: b.support_email ?? '',
    instance_url: b.instance_url ?? '',
    legal_entity: b.legal_entity ?? '',
    welcome_message: b.welcome_message ?? '',
  }
}

export function InstanceBrandingPage() {
  const { branding, isLoading, refresh } = useBranding()
  const [form, setForm] = useState<FormState>(toForm(branding))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setForm(toForm(branding))
  }, [branding])

  const previewName = form.instance_name.trim() || 'BigMCP'
  const previewColor = form.primary_color.trim() || '#D97757'
  const previewLogo = form.logo_url.trim()

  const dirty = useMemo(() => {
    const cur = toForm(branding)
    return (Object.keys(form) as (keyof FormState)[]).some((k) => form[k] !== cur[k])
  }, [form, branding])

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      // Send all fields; empty string tells the backend to clear back
      // to env/default. That mirrors what users see in the form: a
      // blank input means "use defaults".
      await api.patch('/admin/instance/branding', form)
      await refresh()
      toast.success('Branding updated.')
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      const msg =
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
            ? detail.map((d: any) => d.msg || JSON.stringify(d)).join(' — ')
            : e.message || 'Update failed'
      setError(msg)
      toast.error(msg)
    } finally {
      setSaving(false)
    }
  }

  const handleResetAll = async () => {
    if (!confirm('Clear every branding override and fall back to defaults?')) return
    const empty: FormState = {
      instance_name: '',
      instance_tagline: '',
      logo_url: '',
      favicon_url: '',
      primary_color: '#D97757',
      support_email: '',
      instance_url: '',
      legal_entity: '',
      welcome_message: '',
    }
    setForm(empty)
    setSaving(true)
    try {
      await api.patch('/admin/instance/branding', empty)
      await refresh()
      toast.success('Branding reset to defaults.')
    } catch (e: any) {
      toast.error('Reset failed.')
    } finally {
      setSaving(false)
    }
  }

  const Field = ({
    label,
    name,
    placeholder,
    type = 'text',
    hint,
  }: {
    label: string
    name: keyof FormState
    placeholder?: string
    type?: 'text' | 'email' | 'url'
    hint?: string
  }) => (
    <label className="block">
      <div className="text-sm font-semibold text-gray-700 mb-1">{label}</div>
      <input
        type={type}
        value={form[name]}
        onChange={(e) => setForm((f) => ({ ...f, [name]: e.target.value }))}
        placeholder={placeholder}
        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-orange focus:border-orange"
      />
      {hint && <p className="mt-1 text-xs text-gray-500">{hint}</p>}
    </label>
  )

  return (
    <div className="container mx-auto px-4 py-8 max-w-6xl">
      <div className="flex items-baseline justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <BuildingOfficeIcon className="w-6 h-6 text-orange" />
            Instance branding
          </h1>
          <p className="text-sm text-gray-600 mt-1">
            White-label this deploy. Every field is optional — blank falls back to environment
            variables, then to the built-in BigMCP defaults.
          </p>
        </div>
        {branding.customized && (
          <Badge variant="default" className="bg-green-100 text-green-700">
            <CheckCircleIcon className="w-4 h-4 inline mr-1" />
            Customized
          </Badge>
        )}
      </div>

      {error && (
        <Card padding="md" className="mb-4 border-red-200 bg-red-50">
          <p className="text-sm text-red-700">{error}</p>
        </Card>
      )}

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Form */}
        <div className="lg:col-span-2 space-y-4">
          <Card padding="md">
            <h2 className="text-sm font-semibold text-gray-900 mb-3">Identity</h2>
            <div className="space-y-3">
              <Field label="Instance name" name="instance_name" placeholder="e.g. Acme MCP" />
              <Field
                label="Tagline"
                name="instance_tagline"
                placeholder="Unified MCP Gateway for AI Agents"
              />
              <Field
                label="Legal entity"
                name="legal_entity"
                placeholder="e.g. Acme Inc."
                hint="Shown in the footer of emails."
              />
            </div>
          </Card>

          <Card padding="md">
            <h2 className="text-sm font-semibold text-gray-900 mb-3">Visuals</h2>
            <div className="space-y-3">
              <Field
                label="Logo URL"
                name="logo_url"
                type="url"
                placeholder="https://… or data:image/svg+xml;base64,…"
                hint="Square works best. Empty → built-in dotted-circle BigMCP mark."
              />
              <Field
                label="Favicon URL"
                name="favicon_url"
                type="url"
                placeholder="https://…/favicon.ico"
                hint="Loaded as the browser tab icon. Empty → keeps /favicon.ico."
              />
              <label className="block">
                <div className="text-sm font-semibold text-gray-700 mb-1">Primary color</div>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={form.primary_color || '#D97757'}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, primary_color: e.target.value }))
                    }
                    className="h-10 w-14 border border-gray-300 rounded cursor-pointer"
                  />
                  <input
                    type="text"
                    value={form.primary_color}
                    onChange={(e) =>
                      setForm((f) => ({ ...f, primary_color: e.target.value }))
                    }
                    placeholder="#D97757"
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-orange focus:border-orange"
                  />
                </div>
                <p className="mt-1 text-xs text-gray-500">CSS hex like #D97757.</p>
              </label>
            </div>
          </Card>

          <Card padding="md">
            <h2 className="text-sm font-semibold text-gray-900 mb-3">Contact & URLs</h2>
            <div className="space-y-3">
              <Field
                label="Support email"
                name="support_email"
                type="email"
                placeholder="support@example.com"
              />
              <Field
                label="Instance URL"
                name="instance_url"
                type="url"
                placeholder="https://mcp.example.com"
                hint="Used by composition results and MCP responses so external systems link back to your domain, not bigmcp.cloud."
              />
            </div>
          </Card>

          <Card padding="md">
            <h2 className="text-sm font-semibold text-gray-900 mb-1">Welcome message</h2>
            <p className="text-xs text-gray-600 mb-3">
              Shown on the public landing page (<code>/</code>) when this is a self-hosted
              instance with branding customized. Markdown-lite: paragraphs separated by
              blank lines, inline links as <code>[label](url)</code>. Keep it under ~4KB
              — longer onboarding belongs in <code>/docs</code>.
            </p>
            <textarea
              value={form.welcome_message}
              onChange={(e) =>
                setForm((f) => ({ ...f, welcome_message: e.target.value }))
              }
              rows={6}
              maxLength={4096}
              placeholder="Welcome to our internal MCP gateway. Sign in with your work account to access [your docs](https://docs.example.com)."
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-orange focus:border-orange"
            />
            <p className="mt-1 text-xs text-gray-500 text-right">
              {form.welcome_message.length} / 4096
            </p>
          </Card>

          <div className="flex items-center justify-between pt-2">
            <Button variant="ghost" onClick={handleResetAll} disabled={saving}>
              Reset to defaults
            </Button>
            <Button
              variant="primary"
              onClick={handleSave}
              disabled={!dirty || saving || isLoading}
            >
              {saving ? (
                <ArrowPathIcon className="w-4 h-4 animate-spin" />
              ) : (
                'Save branding'
              )}
            </Button>
          </div>
        </div>

        {/* Live preview */}
        <div>
          <div className="sticky top-6 space-y-3">
            <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
              Live preview
            </h2>
            <Card padding="md">
              <p className="text-xs text-gray-500 mb-2">Navbar</p>
              <div className="flex items-center gap-2 border border-gray-200 rounded-lg p-3 bg-white">
                {previewLogo ? (
                  <img
                    src={previewLogo}
                    alt={previewName}
                    className="h-8 w-8 object-contain"
                    onError={(e) => {
                      ;(e.target as HTMLImageElement).style.display = 'none'
                    }}
                  />
                ) : (
                  <div
                    className="h-8 w-8 rounded-full border-2"
                    style={{ borderColor: previewColor }}
                  />
                )}
                <span className="font-bold text-gray-900">{previewName}</span>
              </div>
            </Card>

            <Card padding="md">
              <p className="text-xs text-gray-500 mb-2">Primary button</p>
              <button
                type="button"
                style={{ backgroundColor: previewColor }}
                className="px-4 py-2 text-white rounded font-medium"
              >
                Primary action
              </button>
            </Card>

            <Card padding="md">
              <p className="text-xs text-gray-500 mb-2">Email header</p>
              <div
                className="text-white text-center py-4 px-4 rounded-t"
                style={{ backgroundColor: previewColor }}
              >
                <span className="text-lg font-bold">{previewName}</span>
              </div>
              <div className="border border-t-0 border-gray-200 p-3 text-xs text-gray-600 rounded-b">
                Reset your {previewName} password<br />
                <span className="opacity-50">
                  © {previewName} — MCP Server Management Platform
                </span>
              </div>
            </Card>

            <Card padding="md" className="bg-amber-50 border-amber-200">
              <p className="text-xs text-amber-800">
                <strong>Tip:</strong> on a non-SaaS deploy, customizing branding swaps the
                public landing page (<code>/</code>) for a sober welcome screen with your
                logo, name and tagline — see <code>Welcome message</code> above to add
                your own intro text.
              </p>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}
