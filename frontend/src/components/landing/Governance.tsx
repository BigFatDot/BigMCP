/**
 * Governance — light section pairing RBAC copy with role bars.
 *
 * Left column: eyebrow, title, lead, chip list of guarantees.
 * Right column: 4 role rows, each with a 4-bar level indicator + name +
 * description. The bars fill up by `lv` (Owner 4, Viewer 1).
 */

import { Eyebrow } from './Eyebrow'

interface Role {
  r: string
  d: string
  lv: 1 | 2 | 3 | 4
}

const ROLES: Role[] = [
  { r: 'Owner', d: 'Full control of the org, billing & members', lv: 4 },
  { r: 'Admin', d: 'Manage servers, groups, keys & policies', lv: 3 },
  { r: 'Member', d: 'Use assigned Tool Groups, run tools', lv: 2 },
  { r: 'Viewer', d: 'Read-only visibility into the catalogue', lv: 1 },
]

const CHIPS = [
  'User › Org › Server credentials',
  'HMAC-signed audit trail',
  'Closed registry mode',
  'Air-gap mode',
  'OAuth 2.0 + PKCE',
]

export function Governance() {
  return (
    <section className="landing-section" id="governance">
      <div className="container">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-start">
          {/* Copy column */}
          <div className="reveal">
            <Eyebrow>Governance</Eyebrow>
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
              Full control over who sees what
            </h2>
            <p
              className="landing-lead"
              style={{ marginTop: 18 }}
            >
              Four roles, hierarchical credentials, and immutable audit logs with HMAC-SHA256
              integrity. Run a hardened, closed deployment with the marketplace disabled and custom
              servers only.
            </p>

            <div
              className="flex flex-wrap gap-2.5"
              style={{ marginTop: 28 }}
            >
              {CHIPS.map((c) => (
                <span
                  key={c}
                  className="inline-flex items-center gap-2 font-mono"
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: 'var(--ink-2)',
                    background: 'var(--surface)',
                    border: '1px solid var(--line)',
                    borderRadius: 999,
                    padding: '7px 12px',
                    letterSpacing: '0.02em',
                  }}
                >
                  <span
                    aria-hidden="true"
                    style={{
                      width: 6,
                      height: 6,
                      borderRadius: '50%',
                      background: 'var(--accent)',
                    }}
                  />
                  {c}
                </span>
              ))}
            </div>
          </div>

          {/* Roles column */}
          <div className="reveal d2 flex flex-col gap-3">
            {ROLES.map((role) => (
              <div
                key={role.r}
                className="flex items-center gap-5"
                style={{
                  background: 'var(--surface)',
                  border: '1px solid var(--line)',
                  borderRadius: 14,
                  padding: '18px 20px',
                  boxShadow: 'var(--shadow-sm)',
                }}
              >
                <div
                  className="flex items-end gap-1 flex-none"
                  aria-label={`Level ${role.lv} of 4`}
                >
                  {[1, 2, 3, 4].map((b) => {
                    const on = b <= role.lv
                    return (
                      <span
                        key={b}
                        style={{
                          width: 6,
                          height: 8 + b * 4,
                          borderRadius: 2,
                          background: on ? 'var(--accent)' : 'var(--line-2)',
                          display: 'inline-block',
                        }}
                      />
                    )
                  })}
                </div>
                <div className="flex flex-col gap-1 min-w-0">
                  <span
                    className="font-sans font-bold"
                    style={{
                      fontSize: 16,
                      letterSpacing: '-0.005em',
                      color: 'var(--ink)',
                    }}
                  >
                    {role.r}
                  </span>
                  <span
                    className="font-serif"
                    style={{
                      fontSize: 14,
                      lineHeight: 1.5,
                      color: 'var(--ink-2)',
                    }}
                  >
                    {role.d}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
