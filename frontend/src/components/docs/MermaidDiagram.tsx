/**
 * MermaidDiagram - Renders Mermaid diagrams in documentation
 *
 * Supports flowcharts, sequence diagrams, class diagrams, etc.
 * Uses client-side rendering with mermaid.js
 */

import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'

// Initialize mermaid with custom theme
mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  themeVariables: {
    // Brand colors
    primaryColor: '#F97316', // orange-500
    primaryTextColor: '#fff',
    primaryBorderColor: '#EA580C', // orange-600
    secondaryColor: '#F3F4F6', // gray-100
    secondaryTextColor: '#374151', // gray-700
    tertiaryColor: '#FFF7ED', // orange-50
    // Lines and arrows
    lineColor: '#9CA3AF', // gray-400
    // Background
    background: '#FFFFFF',
    mainBkg: '#FFFFFF',
    // Text
    textColor: '#1F2937', // gray-800
    // Flowchart specific
    nodeBorder: '#D1D5DB', // gray-300
    clusterBkg: '#F9FAFB', // gray-50
    clusterBorder: '#E5E7EB', // gray-200
    // Sequence diagram
    actorBkg: '#F97316',
    actorTextColor: '#fff',
    actorLineColor: '#9CA3AF',
    signalColor: '#374151',
    signalTextColor: '#374151',
  },
  flowchart: {
    htmlLabels: true,
    curve: 'basis',
    padding: 15,
  },
  sequence: {
    diagramMarginX: 50,
    diagramMarginY: 10,
    actorMargin: 50,
    width: 150,
    height: 65,
    boxMargin: 10,
    boxTextMargin: 5,
    noteMargin: 10,
    messageMargin: 35,
  },
})

interface MermaidDiagramProps {
  chart: string
  caption?: string
}

export function MermaidDiagram({ chart, caption }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [svg, setSvg] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const renderDiagram = async () => {
      if (!containerRef.current) return

      setIsLoading(true)
      setError(null)

      try {
        // Generate unique ID for this diagram
        const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`

        // Render the diagram
        const { svg: renderedSvg } = await mermaid.render(id, chart)
        setSvg(renderedSvg)
      } catch (err) {
        console.error('Mermaid rendering error:', err)
        setError(err instanceof Error ? err.message : 'Failed to render diagram')
      } finally {
        setIsLoading(false)
      }
    }

    renderDiagram()
  }, [chart])

  if (error) {
    return (
      <div className="my-6 p-4 bg-red-50 border border-red-200 rounded-lg">
        <p className="text-sm text-red-600 font-medium">Failed to render diagram</p>
        <pre className="mt-2 text-xs text-red-500 overflow-x-auto">{error}</pre>
        <details className="mt-2">
          <summary className="text-xs text-red-400 cursor-pointer">View source</summary>
          <pre className="mt-2 p-2 bg-red-100 rounded text-xs overflow-x-auto">{chart}</pre>
        </details>
      </div>
    )
  }

  return (
    <figure className="my-6">
      <div
        ref={containerRef}
        className={`
          flex justify-center p-6 bg-white border border-gray-200 rounded-lg
          overflow-x-auto
          ${isLoading ? 'animate-pulse bg-gray-50' : ''}
        `}
      >
        {isLoading ? (
          <div className="h-32 w-full flex items-center justify-center">
            <div className="flex items-center gap-2 text-gray-400">
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                  fill="none"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              <span className="text-sm">Rendering diagram...</span>
            </div>
          </div>
        ) : (
          <div
            dangerouslySetInnerHTML={{ __html: svg }}
            className="mermaid-diagram [&_svg]:max-w-full"
          />
        )}
      </div>
      {caption && (
        <figcaption className="mt-2 text-center text-sm text-gray-500 italic">
          {caption}
        </figcaption>
      )}
    </figure>
  )
}

export default MermaidDiagram
