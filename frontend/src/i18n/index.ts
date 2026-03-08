import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import Backend from 'i18next-http-backend'
import { SUPPORTED_LANGUAGES } from './languages'

/**
 * i18n — lazy loading via HTTP backend
 *
 * Locale files are served as static JSON from /locales/{lang}/{ns}.json
 * Only the active language is fetched — zero bundle cost for unused languages.
 * Adding a new language: add entry in languages.ts + files in public/locales/<code>/
 */

const namespaces = ['common', 'auth', 'settings', 'marketplace', 'dashboard', 'landing', 'docs']
const supportedLngs = SUPPORTED_LANGUAGES.map((l) => l.code)

i18n
  .use(Backend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: 'en',
    supportedLngs,
    defaultNS: 'common',
    ns: namespaces,

    backend: {
      loadPath: '/locales/{{lng}}/{{ns}}.json',
    },

    detection: {
      order: ['localStorage', 'navigator', 'htmlTag'],
      caches: ['localStorage'],
      lookupLocalStorage: 'bigmcp_language',
    },

    interpolation: {
      escapeValue: false,
    },

    react: {
      useSuspense: true,
    },

    debug: import.meta.env.DEV,
  })

i18n.on('languageChanged', (lng: string) => {
  document.documentElement.lang = lng
})

export default i18n
