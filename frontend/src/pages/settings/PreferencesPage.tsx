/**
 * Preferences Page
 *
 * User preferences including theme, notifications, and language.
 * Organization switching is available in the Team page.
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  BellIcon,
  LanguageIcon,
} from '@heroicons/react/24/outline'
import { Button, Card } from '@/components/ui'
import toast from 'react-hot-toast'
import { SUPPORTED_LANGUAGES } from '@/i18n/languages'

interface Preferences {
  notifications: {
    email_updates: boolean
    server_alerts: boolean
    composition_results: boolean
    weekly_digest: boolean
  }
}

const STORAGE_KEY = 'bigmcp_preferences'

const defaultPreferences: Preferences = {
  notifications: {
    email_updates: true,
    server_alerts: true,
    composition_results: true,
    weekly_digest: false,
  },
}

function loadPreferences(): Preferences {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) return JSON.parse(stored)
  } catch { /* ignore parse errors */ }
  return defaultPreferences
}

export function PreferencesPage() {
  const { t, i18n } = useTranslation('settings')

  const [preferences, setPreferences] = useState<Preferences>(loadPreferences)
  const [isSaving, setIsSaving] = useState(false)

  const handleNotificationChange = (key: keyof Preferences['notifications'], value: boolean) => {
    setPreferences((prev) => ({
      ...prev,
      notifications: { ...prev.notifications, [key]: value },
    }))
  }

  const handleLanguageChange = (lang: string) => {
    i18n.changeLanguage(lang)
  }

  const handleSave = () => {
    setIsSaving(true)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences))
      toast.success(t('preferences.saved', 'Preferences saved'))
    } catch {
      toast.error(t('preferences.saveFailed', 'Failed to save preferences'))
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="container py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-4xl font-bold text-gray-900 mb-2">{t('preferences.title')}</h1>
        <p className="text-lg text-gray-600 font-serif">
          {t('preferences.subtitle')}
        </p>
      </div>

      {/* Notifications */}
      <Card padding="lg" className="mb-6">
        <div className="flex items-center gap-3 mb-4">
          <BellIcon className="w-6 h-6 text-gray-600" />
          <h2 className="text-lg font-semibold text-gray-900">{t('preferences.notifications.title')}</h2>
        </div>

        <div className="space-y-4">
          {[
            { key: 'email_updates', labelKey: 'emailUpdates', descKey: 'emailUpdates' },
            { key: 'server_alerts', labelKey: 'serverAlerts', descKey: 'serverAlerts' },
            { key: 'composition_results', labelKey: 'compositionResults', descKey: 'compositionResults' },
            { key: 'weekly_digest', labelKey: 'weeklyDigest', descKey: 'weeklyDigest' },
          ].map((item) => (
            <label
              key={item.key}
              className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 cursor-pointer"
            >
              <div>
                <p className="font-medium text-gray-900">{t(`preferences.notifications.${item.labelKey}`)}</p>
                <p className="text-sm text-gray-600">{t(`preferences.notifications.${item.descKey}Desc`)}</p>
              </div>
              <input
                type="checkbox"
                checked={preferences.notifications[item.key as keyof Preferences['notifications']]}
                onChange={(e) =>
                  handleNotificationChange(
                    item.key as keyof Preferences['notifications'],
                    e.target.checked
                  )
                }
                className="rounded border-gray-300 text-orange focus:ring-orange"
              />
            </label>
          ))}
        </div>
      </Card>

      {/* Language */}
      <Card padding="lg" className="mb-6">
        <div className="flex items-center gap-3 mb-4">
          <LanguageIcon className="w-6 h-6 text-gray-600" />
          <h2 className="text-lg font-semibold text-gray-900">{t('preferences.language.title')}</h2>
        </div>

        <select
          value={i18n.language}
          onChange={(e) => handleLanguageChange(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange focus:border-orange"
        >
          {SUPPORTED_LANGUAGES.map((lang) => (
            <option key={lang.code} value={lang.code}>
              {lang.nativeName}
            </option>
          ))}
        </select>
      </Card>

      {/* Save Button */}
      <div className="flex justify-end">
        <Button variant="primary" onClick={handleSave} disabled={isSaving}>
          {isSaving ? t('preferences.saving') : t('preferences.saveButton')}
        </Button>
      </div>
    </div>
  )
}
