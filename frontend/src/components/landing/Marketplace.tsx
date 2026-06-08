/**
 * Marketplace section: heading + two seamlessly-looping marquee rows of
 * integration chips (forward + reverse), followed by three use-case cards.
 *
 * The 180+ figure is inline plain text for now — `StatStrip.tsx` (built by a
 * sibling agent) exposes a `CountUp` that will be wired in here at final
 * integration time.
 */

import { Eyebrow } from './Eyebrow'
import { Tile } from './Tile'
import { INTEGRATIONS } from './integrations'
import { UseCases } from './UseCases'

/** A single chip in the marquee — square tile + integration name. */
function MarqueeChip({ name, m, c }: { name: string; m: string; c: string }) {
  return (
    <span
      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full flex-none whitespace-nowrap"
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--line)',
        color: 'var(--ink)',
        fontSize: '13px',
        fontWeight: 500,
      }}
    >
      <Tile name={name} m={m} c={c} size={26} radius={8} />
      {name}
    </span>
  )
}

export function Marketplace() {
  // Doubled list so the keyframes can translate -50% and loop seamlessly.
  const row = [...INTEGRATIONS, ...INTEGRATIONS]
  const rowRev = row.slice().reverse()

  return (
    <section className="landing-section" id="marketplace">
      <div className="max-w-[1200px] mx-auto px-6">
        <div className="reveal flex flex-col items-center text-center max-w-3xl mx-auto mb-11">
          <Eyebrow center>Your registry</Eyebrow>
          <h2
            className="mt-3 font-bold tracking-[-.025em]"
            style={{
              fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
              fontSize: 'clamp(28px, 3.4vw, 42px)',
              lineHeight: 1.08,
              color: 'var(--ink)',
            }}
          >
            Your registry + a curated marketplace
          </h2>
          <p className="landing-lead mt-5">
            Declare your private MCP servers. Or pick from a curated{' '}
            <span style={{ color: 'var(--ink)', fontWeight: 600 }}>180+</span> starter pack — npm,
            GitHub, Glama, Smithery. All in one search, behind one URL.
          </p>
        </div>
      </div>

      <div className="landing-marquee-row landing-marquee-mask overflow-hidden">
        <div className="landing-marquee">
          {row.map((it, i) => (
            <MarqueeChip key={`f-${i}`} name={it.name} m={it.m} c={it.c} />
          ))}
        </div>
      </div>
      <div className="landing-marquee-row landing-marquee-mask overflow-hidden mt-3.5">
        <div className="landing-marquee reverse">
          {rowRev.map((it, i) => (
            <MarqueeChip key={`r-${i}`} name={it.name} m={it.m} c={it.c} />
          ))}
        </div>
      </div>

      <div className="max-w-[1200px] mx-auto px-6 mt-16">
        <UseCases />
      </div>
    </section>
  )
}
