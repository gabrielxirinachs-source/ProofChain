/**
 * CitationList — renders source citations with type badges
 */
export default function CitationList({ citations }) {
  const typeColors = {
    'wikidata':  { color: '#06b6d4', label: 'KG' },
    'wikipedia': { color: '#8b5cf6', label: 'WIKI' },
    'news':      { color: '#f59e0b', label: 'NEWS' },
    'academic':  { color: '#10b981', label: 'ACAD' },
    'web':       { color: '#6b7280', label: 'WEB' },
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      {citations.map((citation, i) => {
        const typeKey = citation.source_type?.replace('SourceType.', '').toLowerCase()
        const type = typeColors[typeKey] || typeColors.web

        return (
          <a
            key={i}
            href={citation.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              background: 'var(--bg-panel)',
              border: '1px solid var(--border)',
              borderRadius: '4px',
              padding: '12px 16px',
              textDecoration: 'none',
              transition: 'all 0.2s',
              color: 'inherit',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = type.color
              e.currentTarget.style.background = 'var(--bg-hover)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = 'var(--border)'
              e.currentTarget.style.background = 'var(--bg-panel)'
            }}
          >
            {/* Type badge */}
            <span style={{
              background: `${type.color}18`,
              border: `1px solid ${type.color}44`,
              color: type.color,
              padding: '2px 6px',
              borderRadius: '2px',
              fontSize: '9px',
              letterSpacing: '1px',
              fontWeight: 700,
              flexShrink: 0,
            }}>
              {type.label}
            </span>

            {/* Domain */}
            <span style={{
              fontSize: '11px',
              color: 'var(--text-muted)',
              flexShrink: 0,
              minWidth: '120px',
            }}>
              {citation.domain || new URL(citation.url).hostname}
            </span>

            {/* Title */}
            <span style={{
              fontSize: '13px',
              color: 'var(--text-secondary)',
              flex: 1,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              {citation.title || citation.url}
            </span>

            {/* Reliability */}
            {citation.reliability_score && (
              <span style={{
                fontSize: '11px',
                color: citation.reliability_score >= 0.8
                  ? 'var(--emerald)'
                  : citation.reliability_score >= 0.6
                  ? 'var(--amber)'
                  : 'var(--crimson)',
                flexShrink: 0,
              }}>
                {Math.round(citation.reliability_score * 100)}% trust
              </span>
            )}

            <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>↗</span>
          </a>
        )
      })}
    </div>
  )
}