// Author: Bradley R. Kinnard
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Strategy } from '../api/types'

export function Strategies() {
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [promotionError, setPromotionError] = useState<string | null>(null)

  useEffect(() => {
    loadStrategies()
  }, [])

  async function loadStrategies() {
    try {
      setLoading(true)
      setError(null)
      const response = await api.listStrategies()
      setStrategies(response.strategies)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load strategies')
    } finally {
      setLoading(false)
    }
  }

  async function handlePromote(strategyId: string) {
    try {
      setPromotionError(null)
      await api.promoteStrategy(strategyId)
      loadStrategies()
    } catch (err) {
      setPromotionError(err instanceof Error ? err.message : 'Failed to promote strategy')
    }
  }

  if (loading) {
    return <div className="card">Loading strategies...</div>
  }

  if (error) {
    return (
      <div className="card" style={{ borderColor: 'var(--danger)' }}>
        <h2 style={{ color: 'var(--danger)' }}>Error</h2>
        <p>{error}</p>
        <button className="btn" onClick={loadStrategies} style={{ marginTop: '1rem' }}>Retry</button>
      </div>
    )
  }

  const promotedStrategies = strategies.filter(s => s.promoted)
  const pendingStrategies = strategies.filter(s => !s.promoted && s.gate_passed)
  const unpreparedStrategies = strategies.filter(s => !s.gate_passed)

  return (
    <div>
      <h1>Strategy Evolution</h1>

      {/* Explanation */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h2>How Strategies Evolve</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>
          A <strong>strategy</strong> is a versioned configuration that defines how agents behave.
          Strategies can only be promoted to production if they pass all verification gates.
          This prevents untested or broken strategies from being deployed.
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
          <div style={{ padding: '1rem', background: 'var(--bg-primary)', borderRadius: '8px', borderLeft: '4px solid var(--text-secondary)' }}>
            <div style={{ fontWeight: 'bold', marginBottom: '0.5rem' }}>1. Register</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              A new strategy version is registered with its manifest (capabilities, tools, thresholds).
            </div>
          </div>
          <div style={{ padding: '1rem', background: 'var(--bg-primary)', borderRadius: '8px', borderLeft: '4px solid var(--warning)' }}>
            <div style={{ fontWeight: 'bold', marginBottom: '0.5rem' }}>2. Test</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              The strategy runs through verification gates: replay, integrity, invariants, regression.
            </div>
          </div>
          <div style={{ padding: '1rem', background: 'var(--bg-primary)', borderRadius: '8px', borderLeft: '4px solid var(--success)' }}>
            <div style={{ fontWeight: 'bold', marginBottom: '0.5rem' }}>3. Promote</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              Only if ALL gates pass can the strategy be promoted. No exceptions.
            </div>
          </div>
        </div>
      </div>

      {/* Promotion Error */}
      {promotionError && (
        <div className="card" style={{ marginBottom: '1.5rem', borderColor: 'var(--danger)', background: 'rgba(255,0,0,0.05)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <strong style={{ color: 'var(--danger)' }}>Promotion Blocked:</strong>
              <span style={{ marginLeft: '0.5rem' }}>{promotionError}</span>
            </div>
            <button className="btn" onClick={() => setPromotionError(null)}>Dismiss</button>
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '1rem', textAlign: 'center' }}>
          <div>
            <div style={{ fontSize: '2rem', fontWeight: 'bold', color: 'var(--primary)' }}>{strategies.length}</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Total Strategies</div>
          </div>
          <div>
            <div style={{ fontSize: '2rem', fontWeight: 'bold', color: 'var(--success)' }}>{promotedStrategies.length}</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Promoted</div>
          </div>
          <div>
            <div style={{ fontSize: '2rem', fontWeight: 'bold', color: 'var(--warning)' }}>{pendingStrategies.length}</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Ready to Promote</div>
          </div>
          <div>
            <div style={{ fontSize: '2rem', fontWeight: 'bold' }}>{unpreparedStrategies.length}</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Awaiting Gates</div>
          </div>
        </div>
      </div>

      {/* Strategies List */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2>All Strategies ({strategies.length})</h2>
          <button className="btn" onClick={loadStrategies}>↻ Refresh</button>
        </div>

        {strategies.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-secondary)' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>No strategies registered</div>
            <div>Strategies are registered through the API when agents define their behavior configurations.</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {strategies.map((strategy) => (
              <div key={strategy.strategy_id} style={{
                padding: '1.25rem',
                background: 'var(--bg-primary)',
                borderRadius: '8px',
                borderLeft: `4px solid ${strategy.promoted ? 'var(--success)' : strategy.gate_passed ? 'var(--warning)' : 'var(--text-secondary)'}`
              }}>
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <div>
                    <span style={{ fontWeight: 'bold', fontSize: '1.25rem' }}>{strategy.name}</span>
                    <span style={{ marginLeft: '0.75rem', color: 'var(--text-secondary)' }}>v{strategy.version}</span>
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem' }}>
                    {strategy.promoted ? (
                      <span className="badge badge-success" style={{ padding: '0.5rem 1rem' }}>✓ PROMOTED</span>
                    ) : strategy.gate_passed ? (
                      <span className="badge badge-warning" style={{ padding: '0.5rem 1rem' }}>READY TO PROMOTE</span>
                    ) : (
                      <span className="badge badge-pending" style={{ padding: '0.5rem 1rem' }}>AWAITING GATES</span>
                    )}
                  </div>
                </div>

                {/* Status Row */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
                  <div>
                    <div style={{ color: 'var(--text-secondary)', fontSize: '0.75rem', marginBottom: '0.25rem' }}>Gate Status</div>
                    <div>
                      {strategy.gate_passed ? (
                        <span style={{ color: 'var(--success)' }}>✓ All gates passed</span>
                      ) : (
                        <span style={{ color: 'var(--text-secondary)' }}>Pending verification</span>
                      )}
                    </div>
                  </div>
                  <div>
                    <div style={{ color: 'var(--text-secondary)', fontSize: '0.75rem', marginBottom: '0.25rem' }}>Manifest Hash</div>
                    <div className="hash">{strategy.manifest_hash.slice(0, 24)}...</div>
                  </div>
                </div>

                {/* Scores */}
                {(strategy.correctness_score !== null || strategy.reproducibility_score !== null) && (
                  <div style={{ marginBottom: '1rem' }}>
                    <div style={{ color: 'var(--text-secondary)', fontSize: '0.75rem', marginBottom: '0.5rem' }}>Performance Scores</div>
                    <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                      {strategy.correctness_score !== null && (
                        <div style={{ padding: '0.5rem 1rem', background: 'var(--bg-secondary)', borderRadius: '4px' }}>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Correctness</div>
                          <div style={{ fontWeight: 'bold' }}>{(strategy.correctness_score * 100).toFixed(0)}%</div>
                        </div>
                      )}
                      {strategy.reproducibility_score !== null && (
                        <div style={{ padding: '0.5rem 1rem', background: 'var(--bg-secondary)', borderRadius: '4px' }}>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Reproducibility</div>
                          <div style={{ fontWeight: 'bold' }}>{(strategy.reproducibility_score * 100).toFixed(0)}%</div>
                        </div>
                      )}
                      {strategy.efficiency_score !== null && (
                        <div style={{ padding: '0.5rem 1rem', background: 'var(--bg-secondary)', borderRadius: '4px' }}>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Efficiency</div>
                          <div style={{ fontWeight: 'bold' }}>{(strategy.efficiency_score * 100).toFixed(0)}%</div>
                        </div>
                      )}
                      {strategy.safety_score !== null && (
                        <div style={{ padding: '0.5rem 1rem', background: 'var(--bg-secondary)', borderRadius: '4px' }}>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Safety</div>
                          <div style={{ fontWeight: 'bold' }}>{(strategy.safety_score * 100).toFixed(0)}%</div>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Actions */}
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    className={`btn ${strategy.gate_passed && !strategy.promoted ? 'btn-primary' : ''}`}
                    onClick={() => handlePromote(strategy.strategy_id)}
                    disabled={!strategy.gate_passed || strategy.promoted}
                    title={
                      strategy.promoted ? 'Already promoted' :
                      !strategy.gate_passed ? 'Gates must pass before promotion' :
                      'Promote this strategy to production'
                    }
                  >
                    {strategy.promoted ? '✓ Promoted' : 'Promote'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
