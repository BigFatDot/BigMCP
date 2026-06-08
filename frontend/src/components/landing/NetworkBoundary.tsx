/**
 * NetworkBoundary — visual schematic for the SelfHost section.
 *
 * Layout: a top "outside" row that names the public internet and shows it
 * struck through ("no outbound traffic"), then a bordered VPC box that
 * contains a 2×2 grid of nodes (BigMCP gateway / Local LLM / Private
 * registry / Data plane). The whole thing is plain flex/grid CSS — no SVG.
 */

interface NodeProps {
  name: string
  sub: string
  primary?: boolean
}

function Node({ name, sub, primary = false }: NodeProps) {
  return (
    <div
      className="flex flex-col items-start gap-1"
      style={{
        background: primary ? 'var(--accent-50)' : 'var(--surface)',
        border: `1px solid ${primary ? 'var(--accent-200)' : 'var(--line)'}`,
        borderRadius: 14,
        padding: '16px 18px',
        position: 'relative',
        boxShadow: primary ? '0 6px 18px -10px rgba(217,119,87,.45)' : 'none',
      }}
    >
      {primary && (
        <span
          aria-hidden="true"
          style={{
            position: 'absolute',
            top: 14,
            right: 14,
            width: 10,
            height: 10,
            borderRadius: '50%',
            background: 'var(--accent)',
            boxShadow: '0 0 0 4px rgba(var(--accent-rgb), 0.2)',
          }}
        />
      )}
      <span
        className="font-sans font-bold"
        style={{
          fontSize: 15,
          letterSpacing: '-0.005em',
          color: primary ? 'var(--accent-700)' : 'var(--ink)',
        }}
      >
        {name}
      </span>
      <span
        className="font-mono"
        style={{
          fontSize: 11.5,
          letterSpacing: '0.04em',
          color: primary ? 'var(--accent-700)' : 'var(--ink-3)',
          opacity: 0.9,
        }}
      >
        {sub}
      </span>
    </div>
  )
}

export function NetworkBoundary() {
  return (
    <div className="flex flex-col gap-5">
      {/* Outside the boundary */}
      <div
        className="flex items-center justify-between gap-4 flex-wrap"
        style={{
          padding: '12px 16px',
          borderRadius: 12,
          background: 'transparent',
        }}
      >
        <span
          className="font-mono"
          style={{
            fontSize: 12,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: 'var(--ink-3)',
          }}
        >
          Public internet
        </span>
        <span
          className="inline-flex items-center gap-2 font-mono"
          style={{
            fontSize: 12,
            color: 'var(--ink-3)',
            position: 'relative',
            textDecoration: 'line-through',
            textDecorationColor: 'var(--accent)',
            textDecorationThickness: '1.5px',
          }}
        >
          no outbound traffic
        </span>
      </div>

      {/* VPC box */}
      <div
        style={{
          position: 'relative',
          border: '1.5px dashed var(--line-2)',
          borderRadius: 20,
          padding: 'clamp(20px, 3vw, 32px)',
          background: 'var(--paper)',
        }}
      >
        <span
          className="font-mono"
          style={{
            position: 'absolute',
            top: -10,
            left: 22,
            background: 'var(--surface)',
            border: '1px solid var(--line)',
            padding: '2px 10px',
            borderRadius: 999,
            fontSize: 11,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'var(--ink-2)',
            fontWeight: 600,
          }}
        >
          Your network · VPC
        </span>

        <div
          className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4"
          style={{ marginTop: 6 }}
        >
          <Node name="BigMCP gateway" sub="one governed URL" primary />
          <Node name="Local LLM" sub="Ollama · vLLM" />
          <Node name="Private registry" sub="your MCP servers" />
          <Node name="Data plane" sub="Postgres · Redis · Qdrant" />
        </div>
      </div>
    </div>
  )
}
