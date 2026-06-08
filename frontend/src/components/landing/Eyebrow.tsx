import { cn } from '@/utils/cn'
import type { ReactNode } from 'react'

interface EyebrowProps {
  children: ReactNode
  /** Center-align the eyebrow + its leading dot inside a flex container. */
  center?: boolean
  className?: string
}

/** Uppercase mono section label with a leading orange dot.
 *  Styling lives in `index.css` under `.landing-eyebrow` so the same look
 *  carries over to the SSR-rendered static landing pages. */
export function Eyebrow({ children, center = false, className }: EyebrowProps) {
  return (
    <div className={cn('landing-eyebrow', center && 'justify-center', className)}>
      {children}
    </div>
  )
}
