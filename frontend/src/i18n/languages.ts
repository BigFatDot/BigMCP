/**
 * Supported Languages Registry
 *
 * Single source of truth for all supported languages in the app.
 * To add a new language:
 *   1. Add an entry here
 *   2. Create `src/i18n/locales/<code>/` with all 7 namespace JSON files
 *   (i18n/index.ts auto-discovers locale files via import.meta.glob)
 */

export interface Language {
  code: string
  name: string         // English name
  nativeName: string   // Name in the language itself
  dir?: 'ltr' | 'rtl'
}

export const SUPPORTED_LANGUAGES: Language[] = [
  { code: 'en', name: 'English',    nativeName: 'English' },
  { code: 'fr', name: 'French',     nativeName: 'Français' },
  { code: 'de', name: 'German',     nativeName: 'Deutsch' },
  { code: 'es', name: 'Spanish',    nativeName: 'Español' },
  { code: 'pt', name: 'Portuguese', nativeName: 'Português' },
  { code: 'it', name: 'Italian',    nativeName: 'Italiano' },
  { code: 'nl', name: 'Dutch',      nativeName: 'Nederlands' },
  { code: 'pl', name: 'Polish',     nativeName: 'Polski' },
  { code: 'sv', name: 'Swedish',    nativeName: 'Svenska' },
  { code: 'da', name: 'Danish',     nativeName: 'Dansk' },
  { code: 'no', name: 'Norwegian',  nativeName: 'Norsk' },
  { code: 'el', name: 'Greek',      nativeName: 'Ελληνικά' },
  { code: 'ro', name: 'Romanian',   nativeName: 'Română' },
  { code: 'hr', name: 'Croatian',   nativeName: 'Hrvatski' },
  { code: 'cs', name: 'Czech',      nativeName: 'Čeština' },
  { code: 'hu', name: 'Hungarian',  nativeName: 'Magyar' },
  { code: 'sk', name: 'Slovak',     nativeName: 'Slovenčina' },
  { code: 'fi', name: 'Finnish',    nativeName: 'Suomi' },
  { code: 'bg', name: 'Bulgarian',  nativeName: 'Български' },
  { code: 'uk', name: 'Ukrainian',  nativeName: 'Українська' },
  { code: 'tr', name: 'Turkish',    nativeName: 'Türkçe' },
  { code: 'sr', name: 'Serbian',    nativeName: 'Srpski' },
]

export const LANGUAGE_CODES = SUPPORTED_LANGUAGES.map((l) => l.code)

export function getLanguage(code: string): Language | undefined {
  return SUPPORTED_LANGUAGES.find((l) => l.code === code)
}

export function isSupported(code: string): boolean {
  return LANGUAGE_CODES.includes(code)
}
