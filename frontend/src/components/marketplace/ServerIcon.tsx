/**
 * ServerIcon - Handles image loading with fallback chain
 *
 * Tries URLs in order: primary -> secondary -> avatar
 * Silently falls back on 404 errors.
 */

import { useState, useEffect } from 'react'
import { getColorFromString, getInitials } from '@/utils/serverIcons'

export interface IconUrls {
  primary?: string | null
  secondary?: string | null
  fallback?: string
}

export interface ServerIconProps {
  name: string
  iconUrl?: string
  iconUrls?: IconUrls
  className?: string
  size?: 'sm' | 'md' | 'lg' | 'xl'
}

const sizeClasses = {
  sm: 'w-8 h-8 text-sm',
  md: 'w-12 h-12 text-xl',
  lg: 'w-16 h-16 text-2xl',
  xl: 'w-20 h-20 text-3xl',
}

export function ServerIcon({
  name,
  iconUrl,
  iconUrls,
  className = '',
  size = 'md',
}: ServerIconProps) {
  const [currentUrlIndex, setCurrentUrlIndex] = useState(0)
  const [showAvatar, setShowAvatar] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  // Build URL chain: primary -> secondary -> fallback
  const urlChain: string[] = []
  if (iconUrl) urlChain.push(iconUrl)
  if (iconUrls?.primary && iconUrls.primary !== iconUrl) urlChain.push(iconUrls.primary)
  if (iconUrls?.secondary) urlChain.push(iconUrls.secondary)
  if (iconUrls?.fallback) urlChain.push(iconUrls.fallback)

  // Stable key for effect dependency
  const urlKey = urlChain.join('|')

  // Reset state when URLs change
  useEffect(() => {
    setCurrentUrlIndex(0)
    setShowAvatar(urlChain.length === 0)
    setIsLoading(urlChain.length > 0)
  }, [urlKey])

  const handleError = () => {
    if (currentUrlIndex < urlChain.length - 1) {
      // Try next URL in chain
      setCurrentUrlIndex(prev => prev + 1)
    } else {
      // All URLs failed, show avatar
      setShowAvatar(true)
      setIsLoading(false)
    }
  }

  const handleLoad = () => {
    setIsLoading(false)
  }

  const sizeClass = sizeClasses[size]
  const initials = getInitials(name)
  const bgColor = getColorFromString(name)

  if (showAvatar || urlChain.length === 0) {
    return (
      <div
        className={`${sizeClass} rounded-lg flex items-center justify-center text-white font-bold ${className}`}
        style={{ backgroundColor: bgColor }}
        title={name}
      >
        {initials}
      </div>
    )
  }

  return (
    <div className={`${sizeClass} relative ${className}`}>
      {isLoading && (
        <div
          className={`absolute inset-0 rounded-lg flex items-center justify-center text-white font-bold`}
          style={{ backgroundColor: bgColor, opacity: 0.5 }}
        >
          {initials}
        </div>
      )}
      <img
        src={urlChain[currentUrlIndex]}
        alt={`${name} icon`}
        className={`${sizeClass} rounded-lg object-contain bg-white/5 ${isLoading ? 'opacity-0' : 'opacity-100'} transition-opacity`}
        onError={handleError}
        onLoad={handleLoad}
        title={name}
      />
    </div>
  )
}
