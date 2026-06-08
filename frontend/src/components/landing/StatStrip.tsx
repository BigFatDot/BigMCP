/**
 * StatStrip — 4-stat band immediately under the hero.
 *
 * Reinforces the positioning: ownership, breadth of integrations,
 * air-gap capability and AGPLv3. The "180+" entry uses an internal
 * CountUp component that animates from 0 once the strip enters view.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react'

interface CountUpProps {
  to: number
  suffix?: string
}

/** Tween an integer from 0 → `to` with an ease-out cubic curve.
 *  Animation triggers the first time the element is at least 50% visible. */
function CountUp({ to, suffix = '' }: CountUpProps) {
  const [n, setN] = useState(0)
  const ref = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          const dur = 1100
          const t0 = performance.now()
          const tick = (t: number) => {
            const p = Math.min(1, (t - t0) / dur)
            setN(Math.round((1 - Math.pow(1 - p, 3)) * to))
            if (p < 1) requestAnimationFrame(tick)
          }
          requestAnimationFrame(tick)
          io.disconnect()
        }
      },
      { threshold: 0.5 },
    )
    io.observe(el)

    return () => io.disconnect()
  }, [to])

  return (
    <span ref={ref}>
      {n}
      {suffix}
    </span>
  )
}

interface Stat {
  v: ReactNode
  l: string
}

const STATS: Stat[] = [
  { v: 'Own', l: 'Your registry, your servers' },
  { v: <CountUp to={180} suffix="+" />, l: 'Curated starter pack' },
  { v: 'Air-gap', l: 'Run fully offline' },
  { v: 'AGPLv3', l: 'Free, self-host, no limits' },
]

export function StatStrip() {
  return (
    <section
      className="landing-section tight"
      style={{
        borderTop: '1px solid var(--line)',
        borderBottom: '1px solid var(--line)',
        background: 'var(--paper)',
      }}
    >
      <div className="container">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-6">
          {STATS.map((s, i) => (
            <div key={i} className="reveal flex flex-col items-center text-center gap-2">
              <div
                className="font-sans font-bold"
                style={{
                  fontSize: 'clamp(28px, 3.2vw, 38px)',
                  letterSpacing: '-0.02em',
                  color: 'var(--accent)',
                  lineHeight: 1,
                }}
              >
                {s.v}
              </div>
              <div
                className="font-serif"
                style={{
                  fontSize: 14,
                  color: 'var(--ink-2)',
                  lineHeight: 1.4,
                }}
              >
                {s.l}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
