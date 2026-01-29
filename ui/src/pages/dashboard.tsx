// Author: Bradley R. Kinnard
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Belief, GateStatus, RunStatus, Strategy } from '../api/types'

interface SystemHealth {
  status: string
  db: string
  redis: string
  artifacts: string
}

export function Dashboard() {
  const [runs, setRuns] = useState<RunStatus[]>([])
  const [beliefs, setBeliefs] = useState<Belief[]>([])
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [health, setHealth] = useState<SystemHealth | null>(null)
  const [gateStatuses, setGateStatuses] = useState<Record<string, GateStatus>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadAll()
  }, [])

  async function loadAll() {
    try {
      setLoading(true)
      setError(null)

      const [runsRes, beliefsRes, strategiesRes, healthRes] = await Promise.all([
        api.listRuns({ limit: 10 }),
        api.listBeliefs({}),
        api.listStrategies({}),
        api.getHealth(),
      ])

      setRuns(runsRes.runs)
      setBeliefs(beliefsRes.beliefs)
      setStrategies(strategiesRes.strategies)
      setHealth(healthRes)

      // load gate statuses
      const statuses: Record<string, GateStatus> = {}
      await Promise.all(
        runsRes.runs.slice(0, 5).map(async (run) => {
          try {
            statuses[run.run_id] = await api.getGateStatus(run.run_id)
          } catch {
            // no gate yet
          }
        })
      )
      setGateStatuses(statuses)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
        <div style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>Loading IRONROOT...</div>
        <div style={{ color: 'var(--text-secondary)' }}>Connecting to backend services</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="card" style={{ borderColor: 'var(--danger)' }}>
        <h2 style={{ color: 'var(--danger)' }}>Connection Error</h2>
        <p>{error}</p>
        <p style={{ color: 'var(--text-secondary)', marginTop: '1rem' }}>
          Make sure the API server is running: <code>./scripts/run_once.sh</code>
        </p>
        <button className="btn" onClick={loadAll} style={{ marginTop: '1rem' }}>
          Retry Connection
        </button>
      </div>
    )
  }

  const runningRuns = runs.filter(r => r.status === 'running')
  const completedRuns = runs.filter(r => r.status === 'completed')
  const passedGates = Object.values(gateStatuses).filter(g => g.status === 'passed').length
  const promotedStrategies = strategies.filter(s => s.promoted).length

  return (
    <div>
      {/* System Overview */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ marginBottom: '0.5rem' }}>IRONROOT Control Panel</h1>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
          Multi-agent research system with adversarial verification. Agents propose changes,
          verify each other's work, and only strategies that pass all tests can be promoted.
        </p>

        {/* Status Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '1rem' }}>
          <div style={{ background: 'var(--bg-primary)', padding: '1rem', borderRadius: '8px', textAlign: 'center' }}>
            <div style={{ fontSize: '2rem', fontWeight: 'bold', color: health?.status === 'healthy' ? 'var(--success)' : 'var(--danger)' }}>
              {health?.status === 'healthy' ? '●' : '○'}
            </div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>System Status</div>
            <div style={{ fontWeight: 'bold' }}>{health?.status || 'Unknown'}</div>
          </div>

          <div style={{ background: 'var(--bg-primary)', padding: '1rem', borderRadius: '8px', textAlign: 'center' }}>
            <div style={{ fontSize: '2rem', fontWeight: 'bold', color: 'var(--primary)' }}>{runs.length}</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Total Runs</div>
            <div style={{ fontSize: '0.875rem' }}>{runningRuns.length} active</div>
          </div>

          <div style={{ background: 'var(--bg-primary)', padding: '1rem', borderRadius: '8px', textAlign: 'center' }}>
            <div style={{ fontSize: '2rem', fontWeight: 'bold', color: 'var(--success)' }}>{passedGates}</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Gates Passed</div>
            <div style={{ fontSize: '0.875rem' }}>verification checks</div>
          </div>

          <div style={{ background: 'var(--bg-primary)', padding: '1rem', borderRadius: '8px', textAlign: 'center' }}>
            <div style={{ fontSize: '2rem', fontWeight: 'bold' }}>{beliefs.length}</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Beliefs Recorded</div>
            <div style={{ fontSize: '0.875rem' }}>immutable history</div>
          </div>

          <div style={{ background: 'var(--bg-primary)', padding: '1rem', borderRadius: '8px', textAlign: 'center' }}>
            <div style={{ fontSize: '2rem', fontWeight: 'bold' }}>{strategies.length}</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Strategies</div>
            <div style={{ fontSize: '0.875rem' }}>{promotedStrategies} promoted</div>
          </div>
        </div>
      </div>

      {/* How It Works */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h2>How It Works</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginTop: '1rem' }}>
          <div style={{ padding: '1rem', background: 'var(--bg-primary)', borderRadius: '8px', borderLeft: '4px solid var(--primary)' }}>
            <div style={{ fontWeight: 'bold', marginBottom: '0.5rem' }}>1. Create a Run</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              A run is a complete research cycle. Each run has a seed for reproducibility
              and budgets that limit how much work agents can do.
            </div>
          </div>

          <div style={{ padding: '1rem', background: 'var(--bg-primary)', borderRadius: '8px', borderLeft: '4px solid var(--warning)' }}>
            <div style={{ fontWeight: 'bold', marginBottom: '0.5rem' }}>2. Agents Work</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              Proposer suggests changes. Builder implements them. Tester writes tests.
              Verifier tries to break it. Auditor checks everything.
            </div>
          </div>

          <div style={{ padding: '1rem', background: 'var(--bg-primary)', borderRadius: '8px', borderLeft: '4px solid var(--success)' }}>
            <div style={{ fontWeight: 'bold', marginBottom: '0.5rem' }}>3. Gates Verify</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              Replay, integrity, and regression gates must all pass.
              Same inputs + seed must produce the same results.
            </div>
          </div>

          <div style={{ padding: '1rem', background: 'var(--bg-primary)', borderRadius: '8px', borderLeft: '4px solid var(--danger)' }}>
            <div style={{ fontWeight: 'bold', marginBottom: '0.5rem' }}>4. Promote or Fail</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              Only strategies that pass all gates can be promoted.
              Failed agents lose budget permanently. No resets.
            </div>
          </div>
        </div>
      </div>

      {/* Recent Runs */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2>Recent Runs</h2>
          <button className="btn" onClick={loadAll}>↻ Refresh</button>
        </div>

        {runs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-secondary)' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>No runs yet</div>
            <div>Go to <Link to="/runs" className="link">Runs</Link> to create your first research run.</div>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Status</th>
                <th>Phase</th>
                <th>Progress</th>
                <th>Gate</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {runs.slice(0, 5).map((run) => {
                const gate = gateStatuses[run.run_id]
                const totalSteps = run.steps_used + run.steps_remaining
                const progress = totalSteps > 0 ? Math.round((run.steps_used / totalSteps) * 100) : 0

                return (
                  <tr key={run.run_id}>
                    <td>
                      <Link to={`/runs/${run.run_id}`} className="link hash">
                        {run.run_id.slice(0, 16)}...
                      </Link>
                    </td>
                    <td>
                      <span className={`badge badge-${run.status === 'completed' ? 'success' : run.status === 'failed' ? 'danger' : run.status === 'running' ? 'warning' : 'pending'}`}>
                        {run.status}
                      </span>
                    </td>
                    <td>{run.phase}</td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <div style={{
                          width: '60px',
                          height: '8px',
                          background: 'var(--bg-primary)',
                          borderRadius: '4px',
                          overflow: 'hidden'
                        }}>
                          <div style={{
                            width: `${progress}%`,
                            height: '100%',
                            background: 'var(--primary)',
                            transition: 'width 0.3s'
                          }} />
                        </div>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                          {run.steps_used}/{totalSteps}
                        </span>
                      </div>
                    </td>
                    <td>
                      {gate ? (
                        <span className={`badge badge-${gate.status === 'passed' ? 'success' : gate.status === 'failed' ? 'danger' : 'pending'}`}>
                          {gate.status}
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-secondary)' }}>—</span>
                      )}
                    </td>
                    <td>
                      <Link to={`/runs/${run.run_id}`} className="btn" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}>
                        View Details
                      </Link>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}

        {runs.length > 5 && (
          <div style={{ marginTop: '1rem', textAlign: 'center' }}>
            <Link to="/runs" className="link">View all {runs.length} runs →</Link>
          </div>
        )}
      </div>

      {/* Recent Beliefs */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h2>Recent Agent Beliefs</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.875rem' }}>
          Beliefs are immutable records of what agents claimed during runs. Each belief has a hash chain
          so you can verify nothing was tampered with.
        </p>

        {beliefs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-secondary)' }}>
            No beliefs recorded yet. Beliefs are created when agents make claims during runs.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {beliefs.slice(0, 3).map((belief) => (
              <div key={belief.belief_id} style={{
                padding: '1rem',
                background: 'var(--bg-primary)',
                borderRadius: '8px',
                borderLeft: `4px solid ${belief.confidence >= 0.9 ? 'var(--success)' : belief.confidence >= 0.7 ? 'var(--warning)' : 'var(--text-secondary)'}`
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                  <span style={{ fontWeight: 'bold' }}>{belief.agent_id}</span>
                  <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                    {Math.round(belief.confidence * 100)}% confidence
                  </span>
                </div>
                <div style={{ marginBottom: '0.5rem' }}>
                  {typeof belief.content === 'object' && belief.content !== null
                    ? (belief.content as Record<string, unknown>).claim as string || JSON.stringify(belief.content)
                    : String(belief.content)
                  }
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  {belief.topic_tags.map((tag) => (
                    <span key={tag} className="badge badge-pending">{tag}</span>
                  ))}
                  <span className="hash" style={{ marginLeft: 'auto', fontSize: '0.75rem' }}>
                    {belief.content_hash.slice(0, 16)}...
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}

        {beliefs.length > 3 && (
          <div style={{ marginTop: '1rem', textAlign: 'center' }}>
            <Link to="/beliefs" className="link">View all {beliefs.length} beliefs →</Link>
          </div>
        )}
      </div>

      {/* Infrastructure Status */}
      <div className="card">
        <h2>Infrastructure</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '1rem', marginTop: '1rem' }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ color: health?.db === 'ok' ? 'var(--success)' : 'var(--danger)', fontSize: '1.5rem' }}>
              {health?.db === 'ok' ? '●' : '○'}
            </div>
            <div style={{ fontWeight: 'bold' }}>Database</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>PostgreSQL</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ color: health?.redis === 'ok' ? 'var(--success)' : 'var(--danger)', fontSize: '1.5rem' }}>
              {health?.redis === 'ok' ? '●' : '○'}
            </div>
            <div style={{ fontWeight: 'bold' }}>Queue</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Redis</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ color: health?.artifacts === 'ok' ? 'var(--success)' : 'var(--danger)', fontSize: '1.5rem' }}>
              {health?.artifacts === 'ok' ? '●' : '○'}
            </div>
            <div style={{ fontWeight: 'bold' }}>File Store</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Content-addressed</div>
          </div>
        </div>
      </div>
    </div>
  )
}
