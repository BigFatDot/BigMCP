/**
 * Instance Logo + Instance Wordmark
 *
 * Self-hosted-aware wrappers around the built-in BigMCPLogo. When the
 * admin has uploaded a custom logo_url, we render an <img> at the
 * matching size; otherwise we fall back to the dotted-circle BigMCP
 * mark. Instance name is read from BrandingContext.
 *
 * Use these instead of BigMCPLogo / BigMCPLogoWithText anywhere the
 * brand should follow the instance's identity (navbar, login screens,
 * docs sidebar). The original components stay in place for the public
 * marketing site (LandingPage) where the BigMCP product brand is the
 * actual subject.
 */

import { cn } from '@/utils/cn'
import { useBranding } from '@/contexts/BrandingContext'
import { BigMCPLogo, BigMCPLogoWithText } from './BigMCPLogo'

type Size = 'xs' | 'sm' | 'md' | 'lg' | 'xl'

interface InstanceLogoProps {
  size?: Size
  className?: string
}

const IMG_SIZES: Record<Size, string> = {
  xs: 'h-6 w-6',
  sm: 'h-8 w-8',
  md: 'h-10 w-10',
  lg: 'h-20 w-20',
  xl: 'h-32 w-32',
}

export function InstanceLogo({ size = 'md', className }: InstanceLogoProps) {
  const { branding } = useBranding()
  if (branding.logo_url) {
    return (
      <img
        src={branding.logo_url}
        alt={branding.instance_name}
        className={cn('object-contain', IMG_SIZES[size], className)}
      />
    )
  }
  return <BigMCPLogo size={size} className={className} />
}


interface InstanceLogoWithTextProps {
  size?: Size
  textSize?: 'sm' | 'md' | 'lg'
  className?: string
  variant?: 'light' | 'dark'
}

/** Logo + wordmark. Uses the instance brand name when customized; on a
 *  default BigMCP deploy we fall through to the original two-tone
 *  Big/MCP wordmark for pixel-identical visuals. */
export function InstanceLogoWithText({
  size = 'sm',
  textSize = 'md',
  className,
  variant = 'light',
}: InstanceLogoWithTextProps) {
  const { branding } = useBranding()

  if (!branding.customized && !branding.logo_url) {
    // Default deploy → keep the original styled "Big" + "MCP" wordmark.
    return (
      <BigMCPLogoWithText
        size={size}
        textSize={textSize}
        className={className}
        variant={variant}
      />
    )
  }

  const textSizes: Record<'sm' | 'md' | 'lg', string> = {
    sm: 'text-lg',
    md: 'text-xl',
    lg: 'text-2xl',
  }
  const textColor = variant === 'dark' ? 'text-white' : 'text-gray-800'

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <InstanceLogo size={size} />
      <span className={cn('font-bold tracking-tight', textSizes[textSize], textColor)}>
        {branding.instance_name}
      </span>
    </div>
  )
}
