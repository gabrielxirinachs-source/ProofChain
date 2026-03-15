import { useState, useCallback } from 'react'
import { verifyClaim } from './lib/api'
import EvidenceGraph from './components/EvidenceGraph'
import VerdictBadge from './components/VerdictBadge'
import CitationList from './components/CitationList'
import './App.css'

// Example claims to help users get started
const EXAMPLE_CLAIMS = [
  "The Eiffel Tower is located in Paris, France",
  "Albert Einstein was born in Germany",
  "The Great Wall of China is visible from space",
  "Humans only use 10% of their brain",
]

export default function App() {
  const [claim, setClaim] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [phase, setPhase] = useState(null) // tracks loading phase text

  const handleVerify = useCallback(async (claimText) => {
    const text = claimText || claim
    if (!text.trim() || text.length < 10) return

    setLoading(true)
    setResult(null)
    setError(null)
    setPhase('Extracting entities...')

    // Simulate phase updates for UX
    const phases = [
      'Extracting entities...',
      'Querying Wikidata knowledge graph...',
      'Searching web sources...',
      'Evaluating evidence...',
      'Generating verdict...',
    ]
    let phaseIdx = 0
    const phaseTimer = setInterval(() => {
      phaseIdx = Math.min(phaseIdx + 1, phases.length - 1)
      setPhase(phases[phaseIdx])
    }, 4000)

    try {
      const data = await verifyClaim(text)
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      clearInterval(phaseTimer)
      setLoading(false)
      setPhase(null)
    }
  }, [claim])

  const handleExample = (example) => {
    setClaim(example)
    handleVerify(example)
  }

  return (
    <div className="app">
      {/* Scanline effect overlay */}
      <div className="scanline" />

      {/* Header */}
      <header className="header">
        <div className="header-inner">
          <div className="logo">
            <span className="logo-bracket">[</span>
            <span className="logo-text">PROOF</span>
            <span className="logo-chain">CHAIN</span>
            <span className="logo-bracket">]</span>
          </div>
          <p className="tagline">
            multi-agent · evidence-grounded · auditable
          </p>
        </div>
      </header>

      {/* Main content */}
      <main className="main">

        {/* Claim Input */}
        <section className="input-section">
          <div className="input-label">
            <span className="label-prefix">01 //</span> SUBMIT CLAIM FOR ANALYSIS
          </div>

          <div className="input-wrapper">
            <textarea
              className="claim-input"
              value={claim}
              onChange={e => setClaim(e.target.value)}
              placeholder="Enter a claim to fact-check..."
              rows={3}
              disabled={loading}
              onKeyDown={e => {
                if (e.key === 'Enter' && e.metaKey) handleVerify()
              }}
            />
            <button
              className={`verify-btn ${loading ? 'loading' : ''}`}
              onClick={() => handleVerify()}
              disabled={loading || claim.length < 10}
            >
              {loading ? (
                <span className="btn-loading">
                  <span className="spinner" />
                  ANALYZING
                </span>
              ) : (
                <span>VERIFY →</span>
              )}
            </button>
          </div>

          {/* Phase indicator */}
          {loading && phase && (
            <div className="phase-indicator">
              <span className="phase-dot" />
              {phase}
            </div>
          )}

          {/* Example claims */}
          {!loading && !result && (
            <div className="examples">
              <span className="examples-label">try an example:</span>
              {EXAMPLE_CLAIMS.map(ex => (
                <button
                  key={ex}
                  className="example-btn"
                  onClick={() => handleExample(ex)}
                >
                  {ex}
                </button>
              ))}
            </div>
          )}
        </section>

        {/* Error */}
        {error && (
          <div className="error-panel">
            <span className="error-icon">⚠</span>
            <span>{error}</span>
          </div>
        )}

        {/* Results */}
        {result && (
          <div className="results" style={{ animation: 'fadeIn 0.4s ease' }}>

            {/* Verdict header */}
            <section className="verdict-section">
              <div className="input-label">
                <span className="label-prefix">02 //</span> VERDICT
                {result.cached && <span className="cached-badge">CACHED</span>}
              </div>

              <div className="verdict-header">
                <VerdictBadge verdict={result.verdict} confidence={result.confidence} />
                <div className="verdict-meta">
                  <div className="meta-item">
                    <span className="meta-label">CONFIDENCE</span>
                    <span className="meta-value">
                      {Math.round(result.confidence * 100)}%
                    </span>
                  </div>
                  <div className="meta-item">
                    <span className="meta-label">EVIDENCE</span>
                    <span className="meta-value">
                      {result.evidence_graph.node_count} nodes
                    </span>
                  </div>
                  <div className="meta-item">
                    <span className="meta-label">SOURCES</span>
                    <span className="meta-value">
                      {result.citations.length}
                    </span>
                  </div>
                  <div className="meta-item">
                    <span className="meta-label">ITERATIONS</span>
                    <span className="meta-value">
                      {result.iterations_used}
                    </span>
                  </div>
                </div>
              </div>

              {result.verdict_explanation && (
                <div className="explanation">
                  <span className="explanation-label">ANALYSIS //</span>
                  {result.verdict_explanation}
                </div>
              )}
            </section>

            {/* Evidence Graph */}
            {result.evidence_graph.node_count > 0 && (
              <section className="graph-section">
                <div className="input-label">
                  <span className="label-prefix">03 //</span> EVIDENCE GRAPH
                  <span className="graph-legend">
                    <span className="legend-item supporting">● SUPPORTING</span>
                    <span className="legend-item contradicting">● CONTRADICTING</span>
                    <span className="legend-item context">● CONTEXT</span>
                  </span>
                </div>
                <EvidenceGraph
                  claim={result.claim}
                  nodes={result.evidence_graph.nodes}
                  edges={result.evidence_graph.edges}
                />
              </section>
            )}

            {/* Citations */}
            {result.citations.length > 0 && (
              <section className="citations-section">
                <div className="input-label">
                  <span className="label-prefix">04 //</span> CITATIONS
                </div>
                <CitationList citations={result.citations} />
              </section>
            )}

            {/* Failure modes */}
            {result.failure_modes.length > 0 && (
              <section className="failure-section">
                <div className="input-label">
                  <span className="label-prefix">05 //</span> FAILURE MODES
                </div>
                <div className="failure-list">
                  {result.failure_modes.map((fm, i) => (
                    <div key={i} className="failure-item">
                      <span className="failure-icon">⚠</span>
                      {fm}
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* New claim button */}
            <button
              className="new-claim-btn"
              onClick={() => { setResult(null); setClaim('') }}
            >
              ← ANALYZE NEW CLAIM
            </button>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="footer">
        <span>PROOFCHAIN // MULTI-AGENT FACT-CHECKING ENGINE</span>
        <span>BUILT WITH LANGGRAPH + WIKIDATA + FASTAPI</span>
      </footer>
    </div>
  )
}