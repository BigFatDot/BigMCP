/**
 * "How it works" interactive section. Renders two flows (User / Admin) as a
 * toggle and auto-cycles through their steps every 4200ms. Clicking a step
 * locks in that step and the cycle restarts from there at the next tick.
 *
 * Layout: heading + toggle on top, two-column grid below (vertical step
 * list on the left, `StepPanel` preview on the right).
 */

import { useEffect, useState } from 'react'
import { Eyebrow } from './Eyebrow'
import { StepPanel, type PanelKind } from './StepPanel'

interface Step {
  t: string
  d: string
  panel: PanelKind
}

const STEPS_USER: Step[] = [
  {
    t: 'Sign in',
    d: "Use your own account, or your team's SSO. No new identity to manage.",
    panel: 'signin',
  },
  {
    t: 'Pick the tools you need',
    d: "Browse your team's curated catalogue and add only the tools you're cleared for.",
    panel: 'pick',
  },
  {
    t: 'Connect your AI client',
    d: 'Paste one URL into Claude, Cursor or Cline — your tools just work.',
    panel: 'connect',
  },
]

const STEPS_ADMIN: Step[] = [
  {
    t: 'Declare MCP servers',
    d: 'Add to your private registry, or pick from the 180+ curated starter pack.',
    panel: 'register',
  },
  {
    t: 'Auto-discover tools',
    d: 'BigMCP calls tools/list and indexes everything, with semantic search over the catalogue.',
    panel: 'discover',
  },
  {
    t: 'Create Tool Groups',
    d: 'Curate tools per team with PRIVATE / ORGANIZATION / PUBLIC visibility.',
    panel: 'groups',
  },
  {
    t: 'Issue scoped API keys',
    d: 'Per-group keys with 7 granular scopes. bcrypt-hashed, bigmcp_sk_* format.',
    panel: 'keys',
  },
  {
    t: 'Hand over the URL',
    d: 'Every teammate connects Claude, Cursor or Cline with a single URL — and sees only their tools.',
    panel: 'connect',
  },
]

const CYCLE_MS = 4200

type ViewKind = 'user' | 'admin'

export function HowItWorks() {
  const [view, setView] = useState<ViewKind>('user')
  const [i, setI] = useState(0)

  const steps = view === 'user' ? STEPS_USER : STEPS_ADMIN

  // Reset index when toggling User ↔ Admin so the cycle restarts from step 0.
  useEffect(() => {
    setI(0)
  }, [view])

  // Auto-cycle. Restarts (clearInterval + new interval) whenever the user
  // toggles view or clicks a step (since `i` is in the deps array).
  useEffect(() => {
    const id = window.setInterval(() => {
      setI((prev) => (prev + 1) % steps.length)
    }, CYCLE_MS)
    return () => window.clearInterval(id)
  }, [view, i, steps.length])

  return (
    <section className="landing-section" id="how">
      <div className="max-w-[1200px] mx-auto px-6">
        <div className="reveal flex flex-col md:flex-row md:items-end md:justify-between gap-6 mb-12">
          <div className="max-w-2xl">
            <Eyebrow>How it works</Eyebrow>
            <h2
              className="mt-3 font-bold tracking-[-.025em]"
              style={{
                fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
                fontSize: 'clamp(28px, 3.4vw, 42px)',
                lineHeight: 1.08,
                color: 'var(--ink)',
              }}
            >
              From scattered servers to one governed URL
            </h2>
          </div>
          <div
            role="tablist"
            aria-label="View as"
            className="inline-flex items-center gap-1 p-1 rounded-full self-start md:self-auto"
            style={{ background: 'var(--paper)', border: '1px solid var(--line)' }}
          >
            <span
              className="text-[11px] font-semibold uppercase tracking-[.14em] px-3"
              style={{ color: 'var(--ink-3)' }}
            >
              View as
            </span>
            {(['user', 'admin'] as const).map((v) => {
              const on = view === v
              return (
                <button
                  key={v}
                  type="button"
                  role="tab"
                  aria-selected={on}
                  onClick={() => setView(v)}
                  className="text-[12.5px] font-semibold px-3.5 py-1.5 rounded-full transition-colors"
                  style={{
                    background: on ? 'var(--surface)' : 'transparent',
                    color: on ? 'var(--ink)' : 'var(--ink-3)',
                    boxShadow: on ? '0 1px 2px rgba(20,16,12,.08)' : 'none',
                  }}
                >
                  {v === 'user' ? 'User' : 'Admin'}
                </button>
              )
            })}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-10 lg:gap-14 items-start reveal">
          <ol className="flex flex-col gap-2">
            {steps.map((s, idx) => {
              const active = idx === i
              return (
                <li key={`${view}-${idx}`}>
                  <button
                    type="button"
                    onClick={() => setI(idx)}
                    className="w-full text-left flex gap-4 items-start px-4 py-4 rounded-xl transition-colors"
                    style={{
                      background: active ? 'var(--accent-50)' : 'transparent',
                      border: `1px solid ${active ? 'var(--accent-200)' : 'transparent'}`,
                    }}
                    aria-current={active ? 'step' : undefined}
                  >
                    <span
                      className="font-['JetBrains_Mono',ui-monospace,monospace] text-[12px] font-semibold pt-0.5 flex-none"
                      style={{ color: active ? 'var(--accent)' : 'var(--ink-3)' }}
                    >
                      {String(idx + 1).padStart(2, '0')}
                    </span>
                    <span className="flex flex-col gap-1">
                      <span
                        className="text-[15px] font-semibold tracking-[-.005em]"
                        style={{ color: 'var(--ink)' }}
                      >
                        {s.t}
                      </span>
                      <span
                        className="text-[14px] leading-[1.55]"
                        style={{
                          color: 'var(--ink-2)',
                          fontFamily: "'Source Serif 4', Georgia, serif",
                        }}
                      >
                        {s.d}
                      </span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ol>

          {/* `key={view + i}` retriggers the fade-up animation on every step
              change, mirroring the reference implementation. */}
          <div
            key={`${view}-${i}`}
            className="animate-fade-up lg:sticky lg:top-24"
          >
            <StepPanel which={steps[i].panel} />
          </div>
        </div>
      </div>
    </section>
  )
}
