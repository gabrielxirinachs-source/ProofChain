import { useEffect, useRef, useState } from 'react'

/**
 * EvidenceGraph — D3-powered interactive force graph
 *
 * Renders the claim as a central node with evidence nodes
 * connected by colored edges:
 *   green  = supporting evidence
 *   red    = contradicting evidence
 *   blue   = contextual evidence
 *
 * Users can drag nodes to explore the graph.
 */
export default function EvidenceGraph({ claim, nodes, edges }) {
  const svgRef = useRef(null)
  const [tooltip, setTooltip] = useState(null)
  const [selectedNode, setSelectedNode] = useState(null)

  useEffect(() => {
    if (!nodes.length) return

    // Dynamically import D3 to avoid SSR issues
    import('d3').then(d3 => {
      const container = svgRef.current.parentElement
      const width = container.clientWidth
      const height = Math.min(500, Math.max(300, nodes.length * 40))

      // Clear previous render
      d3.select(svgRef.current).selectAll('*').remove()

      const svg = d3.select(svgRef.current)
        .attr('width', width)
        .attr('height', height)

      // Gradient background
      const defs = svg.append('defs')
      const bg = defs.append('radialGradient')
        .attr('id', 'graph-bg')
        .attr('cx', '50%').attr('cy', '50%').attr('r', '50%')
      bg.append('stop').attr('offset', '0%').attr('stop-color', '#0d1422')
      bg.append('stop').attr('offset', '100%').attr('stop-color', '#080c14')

      svg.append('rect')
        .attr('width', width).attr('height', height)
        .attr('fill', 'url(#graph-bg)')
        .attr('rx', 4)

      // Build D3 graph data
      // Claim is node id "claim", evidence nodes use their id
      const graphNodes = [
        { id: 'claim', label: claim, type: 'claim', radius: 28 },
        ...nodes.slice(0, 20).map(n => ({
          id: n.id,
          label: n.text,
          type: n.kg_entity_id ? 'wikidata' : 'web',
          entityId: n.kg_entity_id,
          radius: 14,
        }))
      ]

      const edgeRelationColors = {
        supported_by:       '#10b981',
        contradicted_by:    '#ef4444',
        partially_supports: '#f59e0b',
        context:            '#3b82f6',
        irrelevant:         '#4a5a7a',
      }

      const graphLinks = edges.slice(0, 20).map(e => ({
        source: 'claim',
        target: e.evidence_node_id,
        relation: e.relation_type,
        color: edgeRelationColors[e.relation_type] || '#4a5a7a',
        score: e.relevance_score || 0.5,
      }))

      // Force simulation
      const simulation = d3.forceSimulation(graphNodes)
        .force('link', d3.forceLink(graphLinks)
          .id(d => d.id)
          .distance(d => 120 + (1 - d.score) * 60)
        )
        .force('charge', d3.forceManyBody().strength(-200))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(d => d.radius + 10))

      // Arrow markers for directed edges
      Object.entries(edgeRelationColors).forEach(([rel, color]) => {
        defs.append('marker')
          .attr('id', `arrow-${rel}`)
          .attr('viewBox', '0 -5 10 10')
          .attr('refX', 20).attr('refY', 0)
          .attr('markerWidth', 4).attr('markerHeight', 4)
          .attr('orient', 'auto')
          .append('path')
          .attr('d', 'M0,-5L10,0L0,5')
          .attr('fill', color)
          .attr('opacity', 0.7)
      })

      // Draw links
      const link = svg.append('g').selectAll('line')
        .data(graphLinks)
        .join('line')
        .attr('stroke', d => d.color)
        .attr('stroke-opacity', 0.5)
        .attr('stroke-width', d => 1 + d.score * 1.5)
        .attr('marker-end', d => `url(#arrow-${d.relation})`)

      // Node groups
      const node = svg.append('g').selectAll('g')
        .data(graphNodes)
        .join('g')
        .attr('cursor', 'pointer')
        .call(
          d3.drag()
            .on('start', (event, d) => {
              if (!event.active) simulation.alphaTarget(0.3).restart()
              d.fx = d.x; d.fy = d.y
            })
            .on('drag', (event, d) => {
              d.fx = event.x; d.fy = event.y
            })
            .on('end', (event, d) => {
              if (!event.active) simulation.alphaTarget(0)
              d.fx = null; d.fy = null
            })
        )

      // Node circles
      node.append('circle')
        .attr('r', d => d.radius)
        .attr('fill', d => {
          if (d.type === 'claim') return '#1e3a5f'
          if (d.type === 'wikidata') return '#0d2d1f'
          return '#1a1a2e'
        })
        .attr('stroke', d => {
          if (d.type === 'claim') return '#3b82f6'
          if (d.type === 'wikidata') return '#10b981'
          return '#f59e0b'
        })
        .attr('stroke-width', d => d.type === 'claim' ? 2.5 : 1.5)

      // Node labels (short)
      node.append('text')
        .attr('text-anchor', 'middle')
        .attr('dy', d => d.type === 'claim' ? 5 : 4)
        .attr('fill', d => d.type === 'claim' ? '#93c5fd' : '#6b7280')
        .attr('font-family', "'Space Mono', monospace")
        .attr('font-size', d => d.type === 'claim' ? 9 : 7)
        .attr('pointer-events', 'none')
        .text(d => {
          if (d.type === 'claim') return 'CLAIM'
          if (d.entityId) return d.entityId
          return 'WEB'
        })

      // Tooltip on hover
      node.on('mouseenter', (event, d) => {
        setTooltip({
          x: event.clientX,
          y: event.clientY,
          text: d.label,
          type: d.type,
          entityId: d.entityId,
        })
      })
      .on('mouseleave', () => setTooltip(null))
      .on('click', (event, d) => {
        setSelectedNode(d.id === selectedNode ? null : d)
      })

      // Tick
      simulation.on('tick', () => {
        link
          .attr('x1', d => d.source.x)
          .attr('y1', d => d.source.y)
          .attr('x2', d => d.target.x)
          .attr('y2', d => d.target.y)

        node.attr('transform', d =>
          `translate(${Math.max(d.radius, Math.min(width - d.radius, d.x))},
                     ${Math.max(d.radius, Math.min(height - d.radius, d.y))})`
        )
      })
    })
  }, [nodes, edges, claim])

  return (
    <div style={{ position: 'relative' }}>
      <div style={{
        background: 'var(--bg-panel)',
        border: '1px solid var(--border)',
        borderRadius: '4px',
        overflow: 'hidden',
      }}>
        <svg ref={svgRef} style={{ display: 'block', width: '100%' }} />
      </div>

      {/* Tooltip */}
      {tooltip && (
        <div style={{
          position: 'fixed',
          left: tooltip.x + 12,
          top: tooltip.y - 10,
          background: 'var(--bg-card)',
          border: '1px solid var(--border-bright)',
          borderRadius: '4px',
          padding: '10px 14px',
          maxWidth: '300px',
          fontSize: '12px',
          color: 'var(--text-secondary)',
          lineHeight: 1.5,
          zIndex: 1000,
          pointerEvents: 'none',
          boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
        }}>
          {tooltip.entityId && (
            <div style={{
              fontSize: '10px',
              color: 'var(--emerald)',
              letterSpacing: '1px',
              marginBottom: '4px',
            }}>
              {tooltip.entityId}
            </div>
          )}
          {tooltip.text.slice(0, 200)}{tooltip.text.length > 200 ? '...' : ''}
        </div>
      )}

      {/* Selected node detail panel */}
      {selectedNode && selectedNode !== 'claim' && (
        <div style={{
          marginTop: '12px',
          background: 'var(--bg-panel)',
          border: '1px solid var(--border-bright)',
          borderRadius: '4px',
          padding: '16px',
          fontSize: '13px',
          color: 'var(--text-secondary)',
          lineHeight: 1.6,
          animation: 'fadeIn 0.2s ease',
        }}>
          <div style={{
            fontSize: '10px',
            color: 'var(--amber)',
            letterSpacing: '2px',
            marginBottom: '8px',
          }}>
            SELECTED EVIDENCE //
          </div>
          {selectedNode.label}
        </div>
      )}

      <div style={{
        marginTop: '8px',
        fontSize: '11px',
        color: 'var(--text-muted)',
        textAlign: 'right',
      }}>
        drag nodes to explore · click to inspect
      </div>
    </div>
  )
}