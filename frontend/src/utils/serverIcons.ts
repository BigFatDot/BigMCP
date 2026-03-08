/**
 * Server Icons Utility
 *
 * Provides dynamic icon resolution with fallback to avatars.
 * Icons are loaded from CDNs, with automatic fallback on 404.
 */

/**
 * Generate a consistent color from a string (server name)
 */
export function getColorFromString(str: string): string {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash)
  }

  // Generate a vibrant color (avoid too dark or too light)
  const hue = hash % 360
  const saturation = 65 + (hash % 20) // 65-85%
  const lightness = 50 + (hash % 15) // 50-65%

  return `hsl(${hue}, ${saturation}%, ${lightness}%)`
}

/**
 * Get initials from server name (max 2 characters)
 */
export function getInitials(name: string): string {
  const words = name.trim().split(/\s+/)

  if (words.length === 1) {
    // Single word: take first 2 characters
    return words[0].substring(0, 2).toUpperCase()
  }

  // Multiple words: take first letter of first 2 words
  return (words[0][0] + (words[1]?.[0] || '')).toUpperCase()
}

/**
 * Icon URLs interface from backend curation
 */
export interface IconUrls {
  primary?: string | null
  secondary?: string | null
  fallback?: string
}

/**
 * Generate server icon props for display
 */
export interface ServerIconProps {
  type: 'image' | 'avatar'
  imageUrl?: string
  fallbackUrls?: string[]  // Additional URLs to try on error
  initials?: string
  backgroundColor?: string
}

/**
 * Get icon props with fallback chain support
 * Uses icon_urls from backend curation when available
 */
export function getServerIconProps(
  serverName: string,
  iconUrl?: string,
  iconUrls?: IconUrls
): ServerIconProps {
  // Build fallback chain from backend icon_urls
  const fallbackUrls: string[] = []

  if (iconUrls) {
    if (iconUrls.secondary) fallbackUrls.push(iconUrls.secondary)
    if (iconUrls.fallback) fallbackUrls.push(iconUrls.fallback)
  }

  // Add UI Avatars as final fallback
  const initials = getInitials(serverName)
  const avatarUrl = `https://ui-avatars.com/api/?name=${encodeURIComponent(initials)}&size=64&background=random&color=fff&bold=true`
  fallbackUrls.push(avatarUrl)

  // If explicit icon URL is provided, use it with fallbacks
  if (iconUrl) {
    return {
      type: 'image',
      imageUrl: iconUrl,
      fallbackUrls,
    }
  }

  // Fallback to generated avatar
  return {
    type: 'avatar',
    initials,
    backgroundColor: getColorFromString(serverName),
  }
}

/**
 * Get avatar props only (no image attempt)
 */
export function getAvatarProps(serverName: string): ServerIconProps {
  return {
    type: 'avatar',
    initials: getInitials(serverName),
    backgroundColor: getColorFromString(serverName),
  }
}
