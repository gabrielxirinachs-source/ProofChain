/**
 * VerdictBadge — displays the verdict with color coding and icon
 */
export default function VerdictBadge({ verdict, confidence }) {
  const config = {
    supported: {
      label: 'SUPPORTED',
      icon: '✓',
      color: 'var(--emerald)',
      bg: 'rgba(16,185,129,0.08)',
      border: 'rgba(16,185,129,0.3)',
    },
    contradicted: {
      label: 'CONTRADICTED',
      icon: '✗',
      color: 'var(--crimson)',
      bg: 'rgba(239,68,68,0.08)',
      border: 'rgba(239,68,68,0.3)',
    },
    partially_supported: {
      label: 'PARTIAL',
      icon: '◑',
      color: 'var(--amber)',
      bg: 'rgba(245,158,11,0.08)',
      border: 'rgba(245,158,11,0.3)',
    },
    insufficient: {
      label: 'INSUFFICIENT',
      icon: '?',
      color: 'var(--text-secondary)',
      bg: 'rgba(136,153,187,0.08)',
      border: 'rgba(136,153,187,0.3)',
    },
    unverifiable: {
      label: 'UNVERIFIABLE',
      icon: '∅',
      color: 'var(--text-muted)',
      bg: 'rgba(74,90,122,0.08)',
      border: 'rgba(74,90,122,0.3)',
    },
  }

  const cfg = config[verdict] || config.insufficient

  return (
    <div style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '12px',
      background: cfg.bg,
      border: `1px solid ${cfg.border}`,
      borderRadius: '4px',
      padding: '12px 20px',
    }}>
      <span style={{
        fontSize: '28px',
        color: cfg.color,
        fontFamily: 'var(--font-display)',
        fontWeight: 800,
        lineHeight: 1,
      }}>
        {cfg.icon}
      </span>
      <div>
        <div style={{
          fontSize: '20px',
          fontWeight: 800,
          color: cfg.color,
          fontFamily: 'var(--font-display)',
          letterSpacing: '-0.5px',
          lineHeight: 1,
        }}>
          {cfg.label}
        </div>
        <div style={{
          fontSize: '10px',
          color: 'var(--text-muted)',
          letterSpacing: '2px',
          marginTop: '4px',
        }}>
          VERDICT
        </div>
      </div>
    </div>
  )
}