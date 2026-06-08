/** Integration catalogue used across the landing — orbital hero, marquee,
 *  mock "Pick the tools" panel. These are visual placeholders (mono
 *  lettermarks on brand-coloured tiles), not actual brand marks. */

export interface Integration {
  name: string
  /** Lettermark or short symbol rendered on the tile. */
  m: string
  /** Brand colour for the tile background. */
  c: string
}

export const INTEGRATIONS: Integration[] = [
  { name: 'GitHub',      m: 'gh', c: '#1B1F24' },
  { name: 'Notion',      m: 'N',  c: '#101010' },
  { name: 'Slack',       m: '#',  c: '#4A154B' },
  { name: 'Stripe',      m: 'S',  c: '#635BFF' },
  { name: 'PostgreSQL',  m: 'Pg', c: '#336791' },
  { name: 'Linear',      m: 'L',  c: '#5E6AD2' },
  { name: 'Sentry',      m: 'Se', c: '#362D59' },
  { name: 'Jira',        m: 'J',  c: '#0C66E4' },
  { name: 'Figma',       m: 'Fi', c: '#D63A22' },
  { name: 'Drive',       m: 'Dr', c: '#1FA463' },
  { name: 'Supabase',    m: 'Sb', c: '#1F9D6B' },
  { name: 'Datadog',     m: 'Dd', c: '#632CA6' },
  { name: 'HubSpot',     m: 'Hs', c: '#E8612C' },
  { name: 'Grist',       m: 'Gr', c: '#2C8C6B' },
  { name: 'AWS',         m: 'aws',c: '#C56A12' },
  { name: 'Vercel',      m: '▲',  c: '#111111' },
  { name: 'Airtable',    m: 'A',  c: '#FCB400' },
  { name: 'Cloudflare',  m: 'Cf', c: '#E8801F' },
]
