/**
 * OrbitalGateway — the signature hero visual.
 *
 * A central "one URL" core with 14 integration tiles orbiting on two
 * contra-rotating rings. Hover a tile → it lights up its spoke and the
 * core announces which tool is being routed through the single endpoint.
 *
 * Ported from the Claude Design v2 prototype (orbital.jsx). The orbital
 * geometry is computed analytically via `polar()` and laid out in absolute
 * percentage coordinates inside a square container. Tiles are kept upright
 * thanks to a counter-rotating wrapper (`orbit-counter`).
 */

import { useState, type CSSProperties } from 'react'
import { cn } from '@/utils/cn'
import { BigMCPLogo } from '@/components/brand/BigMCPLogo'
import { Tile, INTEGRATIONS, type Integration } from '@/components/landing'

interface OrbitalGatewayProps {
  className?: string
}

interface RingItem extends Integration {
  _k: number
}

interface OrbitRingProps {
  items: RingItem[]
  /** Ring radius as a percentage (0-50). */
  radius: number
  /** Animation duration in seconds. */
  dur: number
  /** True for the outer ring → spins in reverse. */
  reverse?: boolean
  /** Tile size in px. */
  tile: number
  active: number | null
  setActive: (k: number | null) => void
}

/** Convert polar coordinates (deg from 12 o'clock) into a [x, y] pair
 *  expressed as percentages of the container. */
function polar(cx: number, cy: number, r: number, deg: number): [number, number] {
  const a = ((deg - 90) * Math.PI) / 180
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)]
}

function OrbitRing({ items, radius, dur, reverse = false, tile, active, setActive }: OrbitRingProps) {
  const n = items.length
  const ringStyle: CSSProperties = {
    position: 'absolute',
    inset: 0,
    animation: `spin ${dur}s linear infinite`,
    animationDirection: reverse ? 'reverse' : 'normal',
  }
  const counterStyle: CSSProperties = {
    animation: `spin ${dur}s linear infinite`,
    animationDirection: reverse ? 'normal' : 'reverse',
  }

  return (
    <div style={ringStyle}>
      {/* spokes */}
      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
      >
        {items.map((it, i) => {
          const [x, y] = polar(50, 50, radius, (360 / n) * i)
          const on = active === it._k
          return (
            <line
              key={i}
              x1="50"
              y1="50"
              x2={x}
              y2={y}
              stroke={on ? 'var(--accent)' : 'rgba(217,119,87,0.16)'}
              strokeWidth={on ? 1.1 : 0.5}
              vectorEffect="non-scaling-stroke"
            />
          )
        })}
      </svg>
      {/* tiles */}
      {items.map((it, i) => {
        const [x, y] = polar(50, 50, radius, (360 / n) * i)
        const on = active === it._k
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: `${x}%`,
              top: `${y}%`,
              transform: 'translate(-50%, -50%)',
            }}
          >
            <div style={counterStyle}>
              <div
                onMouseEnter={() => setActive(it._k)}
                onMouseLeave={() => setActive(null)}
                style={{
                  cursor: 'pointer',
                  transition: 'transform .25s ease, filter .25s ease',
                  transform: on ? 'scale(1.12)' : 'scale(1)',
                  filter: on
                    ? 'drop-shadow(0 8px 20px rgba(217,119,87,.45))'
                    : 'drop-shadow(0 2px 6px rgba(20,16,12,.08))',
                }}
              >
                <Tile name={it.name} m={it.m} c={it.c} size={tile} />
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

const DOCK_CLIENTS = ['Claude', 'Cursor', 'Cline', 'Mistral'] as const

export function OrbitalGateway({ className }: OrbitalGatewayProps) {
  const [active, setActive] = useState<number | null>(null)
  const all: RingItem[] = INTEGRATIONS.map((x, i) => ({ ...x, _k: i }))
  const inner = all.slice(0, 6)
  const outer = all.slice(6, 14)
  const activeItem = all.find((x) => x._k === active) ?? null

  // Pause both rings when an item is hovered → keeps the spoke visible.
  const paused = active !== null

  return (
    <div
      className={cn('relative mx-auto', className)}
      style={{
        width: 'min(560px, 100%)',
        aspectRatio: '1 / 1',
        animationPlayState: paused ? 'paused' : 'running',
      }}
    >
      {/* concentric guide rings */}
      <svg
        viewBox="0 0 100 100"
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          pointerEvents: 'none',
        }}
      >
        <circle cx="50" cy="50" r="30" fill="none" stroke="rgba(217,119,87,0.10)" strokeWidth="0.4" vectorEffect="non-scaling-stroke" />
        <circle cx="50" cy="50" r="46" fill="none" stroke="rgba(217,119,87,0.08)" strokeWidth="0.4" vectorEffect="non-scaling-stroke" />
      </svg>

      {/* outer ring — slower, reversed */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          animationPlayState: paused ? 'paused' : 'running',
        }}
      >
        <OrbitRing items={outer} radius={46} dur={92} reverse tile={46} active={active} setActive={setActive} />
      </div>

      {/* inner ring — faster, normal direction */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          animationPlayState: paused ? 'paused' : 'running',
        }}
      >
        <OrbitRing items={inner} radius={30} dur={68} tile={50} active={active} setActive={setActive} />
      </div>

      {/* core */}
      <div
        style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: 160,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 14,
          pointerEvents: 'none',
        }}
      >
        {/* pulsing halos behind the disc */}
        <span
          className="animate-orbital-halo"
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            borderRadius: '50%',
            background:
              'radial-gradient(closest-side, rgba(217,119,87,.35), rgba(217,119,87,0))',
          }}
        />
        <span
          className="animate-orbital-halo"
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            borderRadius: '50%',
            background:
              'radial-gradient(closest-side, rgba(217,119,87,.22), rgba(217,119,87,0))',
            animationDelay: '1.7s',
          }}
        />

        {/* white disc holding the logo */}
        <div
          style={{
            position: 'relative',
            width: 116,
            height: 116,
            borderRadius: '50%',
            background: 'var(--surface)',
            border: '1px solid var(--line)',
            boxShadow: 'var(--shadow-lg)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <BigMCPLogo size="lg" animate />
        </div>

        {/* core label */}
        <div
          style={{
            position: 'relative',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 2,
            textAlign: 'center',
          }}
        >
          {activeItem ? (
            <>
              <span
                style={{
                  fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
                  fontWeight: 700,
                  fontSize: 14,
                  color: 'var(--ink)',
                  letterSpacing: '-0.01em',
                }}
              >
                {activeItem.name}
              </span>
              <span
                style={{
                  fontFamily: "'Source Serif 4', Georgia, serif",
                  fontSize: 12,
                  color: 'var(--ink-3)',
                  fontStyle: 'italic',
                }}
              >
                routed through one URL
              </span>
            </>
          ) : (
            <>
              <span
                style={{
                  fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
                  fontWeight: 700,
                  fontSize: 14,
                  color: 'var(--ink)',
                  letterSpacing: '-0.01em',
                }}
              >
                One MCP endpoint
              </span>
              <span
                className="font-mono"
                style={{
                  fontSize: 12,
                  color: 'var(--accent)',
                }}
              >
                /mcp/sse
              </span>
            </>
          )}
        </div>
      </div>

      {/* client dock */}
      <div
        style={{
          position: 'absolute',
          left: '50%',
          bottom: -8,
          transform: 'translate(-50%, 100%)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <span
          className="landing-eyebrow"
          style={{
            fontSize: 10,
            letterSpacing: '.22em',
          }}
        >
          Any MCP client
        </span>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'center' }}>
          {DOCK_CLIENTS.map((c) => (
            <span
              key={c}
              className="font-mono"
              style={{
                fontSize: 12,
                fontWeight: 500,
                padding: '6px 12px',
                borderRadius: 999,
                background: 'var(--surface)',
                border: '1px solid var(--line)',
                color: 'var(--ink-2)',
                boxShadow: 'var(--shadow-sm)',
              }}
            >
              {c}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
