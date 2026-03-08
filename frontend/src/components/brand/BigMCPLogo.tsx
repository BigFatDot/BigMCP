/**
 * BigMCP Logo Component
 *
 * Logo with 12 balls around an orange core.
 * Flat design without shadows for app consistency.
 */

import { cn } from '@/utils/cn'

interface BigMCPLogoProps {
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  className?: string
  animate?: boolean
}

export function BigMCPLogo({ size = 'md', className, animate = false }: BigMCPLogoProps) {
  const sizes = {
    xs: { container: 'w-6 h-6', ball: 'w-0.5 h-0.5' },
    sm: { container: 'w-8 h-8', ball: 'w-1 h-1' },
    md: { container: 'w-10 h-10', ball: 'w-1.5 h-1.5' },
    lg: { container: 'w-20 h-20', ball: 'w-2.5 h-2.5' },
    xl: { container: 'w-32 h-32', ball: 'w-4 h-4' },
  }

  // 12 positions around the circle (clock positions)
  const positions = [
    { top: '0%', left: '50%' },      // 12h
    { top: '6.7%', left: '75%' },    // 1h
    { top: '25%', left: '93.3%' },   // 2h
    { top: '50%', left: '100%' },    // 3h
    { top: '75%', left: '93.3%' },   // 4h
    { top: '93.3%', left: '75%' },   // 5h
    { top: '100%', left: '50%' },    // 6h
    { top: '93.3%', left: '25%' },   // 7h
    { top: '75%', left: '6.7%' },    // 8h
    { top: '50%', left: '0%' },      // 9h
    { top: '25%', left: '6.7%' },    // 10h
    { top: '6.7%', left: '25%' },    // 11h
  ]

  return (
    <div className={cn('relative', sizes[size].container, className)}>
      {/* Core (orange ball) - flat design, no shadow */}
      <div className="w-full h-full bg-orange rounded-full" />

      {/* Orbiting balls */}
      <div
        className={cn(
          'absolute inset-0',
          animate && 'animate-spin-slow'
        )}
      >
        {positions.map((pos, i) => (
          <div
            key={i}
            className={cn(
              'absolute bg-white rounded-full -translate-x-1/2 -translate-y-1/2',
              sizes[size].ball
            )}
            style={{ top: pos.top, left: pos.left }}
          />
        ))}
      </div>
    </div>
  )
}

/**
 * BigMCP Logo with Text
 *
 * Consistent branding: "Big" in anthracite (light mode) or white (dark mode), "MCP" in orange
 */
interface BigMCPLogoWithTextProps extends BigMCPLogoProps {
  textSize?: 'sm' | 'md' | 'lg'
  /** Use 'dark' for dark backgrounds (Big in white), 'light' for light backgrounds (Big in gray-800) */
  variant?: 'light' | 'dark'
}

export function BigMCPLogoWithText({
  size = 'sm',
  textSize = 'md',
  className,
  animate = false,
  variant = 'light'
}: BigMCPLogoWithTextProps) {
  const textSizes = {
    sm: 'text-lg',
    md: 'text-xl',
    lg: 'text-2xl',
  }

  const bigTextColor = variant === 'dark' ? 'text-white' : 'text-gray-800'

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <BigMCPLogo size={size} animate={animate} />
      <span className={cn('font-bold tracking-tight', textSizes[textSize])}>
        <span className={bigTextColor}>Big</span><span className="text-orange">MCP</span>
      </span>
    </div>
  )
}
