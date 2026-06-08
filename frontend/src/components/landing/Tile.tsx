import { cn } from '@/utils/cn'

interface TileProps {
  /** Accessible name for the tile (e.g. "GitHub"). Shown as a tooltip. */
  name: string
  /** Lettermark or short symbol painted on the tile (e.g. "gh", "N", "#"). */
  m: string
  /** Brand colour for the tile background. */
  c: string
  /** Edge length in pixels. Defaults to 44. */
  size?: number
  /** Override the corner radius. Defaults to `size * 0.28`. */
  radius?: number
  className?: string
}

/** Square brand tile used in the orbital hero, in marquees, and in mock
 *  catalogue panels. JetBrains Mono for the lettermark, soft inset highlight
 *  for a little physicality without leaning on shadows. */
export function Tile({ name, m, c, size = 44, radius, className }: TileProps) {
  const fontSize = m.length > 2 ? size * 0.30 : size * 0.40
  return (
    <div
      className={cn(
        'flex items-center justify-center text-white font-mono font-semibold flex-none',
        className,
      )}
      title={name}
      aria-label={name}
      style={{
        width: size,
        height: size,
        background: c,
        fontSize,
        borderRadius: radius ?? size * 0.28,
        boxShadow:
          '0 1px 2px rgba(20,16,12,.05), inset 0 1px 0 rgba(255,255,255,.18)',
      }}
    >
      {m}
    </div>
  )
}
