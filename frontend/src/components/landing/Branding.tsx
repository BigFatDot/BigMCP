/**
 * Branding — interactive white-label preview.
 *
 * Left column: copy + 8 brand swatches + a hidden `<input type="color">`
 * exposed as a "+" swatch for custom colours + a current-hex readout.
 * Right column: a fake browser window previewing how the picked colour
 * recolours a tenant landing, plus an editable instance_name input.
 *
 * The accent itself lives in the parent (LandingPage), which calls
 * `applyAccent(hex)` to mutate the document-wide CSS variables. That's the
 * trick that lets the *whole* page recolour as the visitor scrolls back up.
 */

import { useState } from 'react'
import { Eyebrow } from './Eyebrow'

interface BrandingProps {
  accent: string
  onAccent: (hex: string) => void
}

interface Swatch {
  c: string
  n: string
}

const BRAND_SWATCHES: Swatch[] = [
  { c: '#D97757', n: 'Terracotta' },
  { c: '#2A6FDB', n: 'Cobalt' },
  { c: '#1F8A5B', n: 'Emerald' },
  { c: '#7A5AE0', n: 'Violet' },
  { c: '#0E7490', n: 'Teal' },
  { c: '#B0413E', n: 'Crimson' },
  { c: '#C2410C', n: 'Ember' },
  { c: '#475569', n: 'Slate' },
]

export function Branding({ accent, onAccent }: BrandingProps) {
  const [name, setName] = useState('AcmeMCP')
  const slug = name.toLowerCase().replace(/[^a-z0-9]/g, '') || 'your'
  const displayName = name || 'Your Co'

  return (
    <section className="landing-section" id="brand" style={{ background: 'var(--paper)' }}>
      <div className="container">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          {/* Copy + controls */}
          <div className="reveal">
            <Eyebrow>White-label · Make it yours</Eyebrow>
            <h2
              className="font-sans font-bold"
              style={{
                fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
                fontSize: 'clamp(28px, 3.6vw, 42px)',
                letterSpacing: '-0.025em',
                lineHeight: 1.08,
                color: 'var(--ink)',
                marginTop: 14,
              }}
            >
              Your BigMCP. <span className="text-orange" style={{ color: accent }}>Your brand.</span>
            </h2>
            <p className="landing-lead" style={{ marginTop: 18 }}>
              Ship a gateway your teams recognize as <em>yours</em>. Set a custom instance name,
              drop in your logo, and pick a primary color — on your own domain, in your own
              palette. No &ldquo;powered by&rdquo;, no compromise.
            </p>

            <div style={{ marginTop: 32 }}>
              <label
                className="font-mono"
                style={{
                  display: 'block',
                  fontSize: 11,
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  color: 'var(--ink-3)',
                  fontWeight: 600,
                  marginBottom: 12,
                }}
              >
                Primary color
              </label>

              <div className="flex flex-wrap gap-2.5" style={{ marginBottom: 16 }}>
                {BRAND_SWATCHES.map((s) => {
                  const on = accent.toLowerCase() === s.c.toLowerCase()
                  return (
                    <button
                      key={s.c}
                      type="button"
                      onClick={() => onAccent(s.c)}
                      title={s.n}
                      aria-label={s.n}
                      aria-pressed={on}
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: 10,
                        background: s.c,
                        border: '2px solid #fff',
                        boxShadow: on
                          ? `0 0 0 2px ${s.c}, 0 4px 12px -4px rgba(20,16,12,.25)`
                          : '0 1px 2px rgba(20,16,12,.08)',
                        cursor: 'pointer',
                        transition: 'transform .15s ease',
                        transform: on ? 'scale(1.05)' : 'scale(1)',
                      }}
                    />
                  )
                })}
                <label
                  title="Custom color"
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 10,
                    border: '1.5px dashed var(--line-2)',
                    background: 'var(--surface)',
                    color: 'var(--ink-3)',
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 18,
                    fontWeight: 500,
                    position: 'relative',
                    overflow: 'hidden',
                  }}
                >
                  <span aria-hidden="true">+</span>
                  <input
                    type="color"
                    value={accent}
                    onChange={(e) => onAccent(e.target.value)}
                    aria-label="Custom color"
                    style={{
                      position: 'absolute',
                      inset: 0,
                      opacity: 0,
                      cursor: 'pointer',
                      border: 'none',
                      padding: 0,
                    }}
                  />
                </label>
              </div>

              <div className="flex items-center gap-3 flex-wrap">
                <span
                  aria-hidden="true"
                  style={{
                    width: 14,
                    height: 14,
                    borderRadius: '50%',
                    background: accent,
                    boxShadow: '0 0 0 3px rgba(var(--accent-rgb), 0.16)',
                  }}
                />
                <span
                  className="font-mono"
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: 'var(--ink)',
                    letterSpacing: '0.04em',
                  }}
                >
                  {accent.toUpperCase()}
                </span>
                <span
                  className="font-serif"
                  style={{ fontSize: 13.5, color: 'var(--ink-3)', lineHeight: 1.5 }}
                >
                  — recolors the entire page live. Scroll up and watch.
                </span>
              </div>
            </div>
          </div>

          {/* Preview window */}
          <div className="reveal d2">
            <div
              style={{
                background: 'var(--surface)',
                border: '1px solid var(--line)',
                borderRadius: 18,
                overflow: 'hidden',
                boxShadow: 'var(--shadow-lg)',
              }}
            >
              {/* fake browser bar */}
              <div
                className="flex items-center gap-2"
                style={{
                  background: 'var(--paper)',
                  borderBottom: '1px solid var(--line)',
                  padding: '10px 14px',
                }}
              >
                {[0, 1, 2].map((d) => (
                  <span
                    key={d}
                    aria-hidden="true"
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: '50%',
                      background: 'var(--line-2)',
                      display: 'inline-block',
                    }}
                  />
                ))}
                <span
                  className="font-mono"
                  style={{
                    marginLeft: 12,
                    fontSize: 11.5,
                    color: 'var(--ink-3)',
                    letterSpacing: '0.02em',
                  }}
                >
                  {slug}.bigmcp.cloud
                </span>
              </div>

              {/* mock body */}
              <div style={{ padding: '24px 24px 32px' }}>
                {/* mock nav */}
                <div className="flex items-center justify-between" style={{ marginBottom: 22 }}>
                  <span className="inline-flex items-center gap-2">
                    <span
                      aria-hidden="true"
                      style={{
                        width: 18,
                        height: 18,
                        borderRadius: '50%',
                        background: accent,
                      }}
                    />
                    <span
                      className="font-sans font-bold"
                      style={{
                        fontSize: 14.5,
                        letterSpacing: '-0.005em',
                        color: 'var(--ink)',
                      }}
                    >
                      {displayName}
                    </span>
                  </span>
                  <span
                    className="font-sans font-semibold"
                    style={{
                      background: accent,
                      color: '#fff',
                      padding: '7px 14px',
                      borderRadius: 8,
                      fontSize: 12.5,
                    }}
                  >
                    Sign in
                  </span>
                </div>

                {/* mock hero */}
                <div className="flex flex-col gap-3">
                  <span
                    className="font-mono inline-flex items-center gap-2"
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      color: accent,
                      letterSpacing: '0.1em',
                      textTransform: 'uppercase',
                    }}
                  >
                    <span aria-hidden="true">●</span> Internal MCP gateway
                  </span>
                  <div
                    className="font-sans font-bold"
                    style={{
                      fontFamily: "'Plus Jakarta Sans', system-ui, sans-serif",
                      fontSize: 28,
                      lineHeight: 1.1,
                      letterSpacing: '-0.025em',
                      color: 'var(--ink)',
                    }}
                  >
                    All your tools.
                    <br />
                    <span style={{ color: accent }}>One endpoint.</span>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap" style={{ marginTop: 10 }}>
                    {[0, 1, 2, 3].map((i) => (
                      <span
                        key={i}
                        aria-hidden="true"
                        style={{
                          width: 44,
                          height: 8,
                          borderRadius: 999,
                          background: accent,
                          opacity: 1 - i * 0.18,
                          display: 'inline-block',
                        }}
                      />
                    ))}
                    <span
                      className="font-sans font-semibold"
                      style={{
                        border: `1.5px solid ${accent}`,
                        color: accent,
                        padding: '5px 12px',
                        borderRadius: 999,
                        fontSize: 12,
                      }}
                    >
                      Get started
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* instance_name input */}
            <div
              className="flex items-center gap-3"
              style={{
                marginTop: 16,
                background: 'var(--surface)',
                border: '1px solid var(--line)',
                borderRadius: 12,
                padding: '10px 14px',
              }}
            >
              <span
                className="font-mono"
                style={{
                  fontSize: 11,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  color: 'var(--ink-3)',
                  fontWeight: 600,
                  flex: 'none',
                }}
              >
                instance_name
              </span>
              <input
                value={name}
                maxLength={18}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your company"
                className="font-sans"
                style={{
                  flex: 1,
                  border: 'none',
                  outline: 'none',
                  background: 'transparent',
                  fontSize: 14,
                  fontWeight: 600,
                  color: 'var(--ink)',
                  letterSpacing: '-0.005em',
                  minWidth: 0,
                }}
              />
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
