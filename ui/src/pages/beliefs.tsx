// Author: Bradley R. Kinnard
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Belief } from '../api/types'

export function Beliefs() {
  const [beliefs, setBeliefs] = useState<Belief[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [runIdFilter, setRunIdFilter] = useState('')
  const [agentFilter, setAgentFilter] = useState('')

  useEffect(() => {
    loadBeliefs()
  }, [])

  async function loadBeliefs() {
    try {
      setLoading(true)
      const params: Record<string, string> = {}
      if (runIdFilter) params.run_id = runIdFilter
      if (agentFilter) params.agent_id = agentFilter
      const response = await api.listBeliefs(Object.keys(params).length > 0 ? params : undefined)
      setBeliefs(response.beliefs)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load beliefs')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <div className="card">Loading beliefs...</div>
  }

  if (error) {
    return (
      <div className="card" style={{ borderColor: 'var(--danger)' }}>
        <h2 style={{ color: 'var(--danger)' }}>Error Loading Beliefs</h2>
        <p>{error}</p>
        <button className="btn" onClick={loadBeliefs} style={{ marginTop: '1rem' }}>Retry</button>
      </div>
    )
  }

  // Group beliefs by run
  const beliefsByRun = beliefs.reduce((acc, belief) => {
    if (!acc[belief.run_id]) acc[belief.run_id] = []
    acc[belief.run_id].push(belief)
    return acc
  }, {} as Record<string, Belief[]>)

  // Get unique agents
  const agents = [...new Set(beliefs.map(b => b.agent_id))].sort()

  return (
    <div>
      <h1>Belief Store</h1>

      {/* Explanation */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h2>What are Beliefs?</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>
          Beliefs are <strong>immutable claims</strong> made by agents during research runs. Once recorded,
          a belief can never be edited or deleted. This creates a permanent, auditable history of what
          each agent thought and when.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
          <div style={{ padding: '1rem', background: 'var(--bg-primary)', borderRadius: '8px' }}>
            <div style={{ fontWeight: 'bold', marginBottom: '0.5rem' }}>Content Hash</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              SHA256 hash of the belief content. Same content always produces same hash.
            </div>
          </div>
          <div style={{ padding: '1rem', background: 'var(--bg-primary)', borderRadius: '8px' }}>
            <div style={{ fontWeight: 'bold', marginBottom: '0.5rem' }}>Parent Hash</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              Links to a previous belief, forming a chain. If anyone tampers with the chain, the hashes won't match.
            </div>
          </div>
          <div style={{ padding: '1rem', background: 'var(--bg-primary)', borderRadius: '8px' }}>
            <div style={{ fontWeight: 'bold', marginBottom: '0.5rem' }}>Confidence</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              How certain the agent is about this claim. Higher confidence = stronger assertion.
            </div>
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h2>Filters</h2>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              Run ID
            </label>
            <input
              type="text"
              placeholder="e.g. run_019c..."
              value={runIdFilter}
              onChange={(e) => setRunIdFilter(e.target.value)}
              style={{
                padding: '0.5rem',
                background: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                borderRadius: '4px',
                color: 'var(--text-primary)',
                width: '200px',
              }}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              Agent
            </label>
            <select
              value={agentFilter}
              onChange={(e) => setAgentFilter(e.target.value)}
              style={{
                padding: '0.5rem',
                background: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                borderRadius: '4px',
                color: 'var(--text-primary)',
                width: '150px',
              }}
            >
              <option value="">All agents</option>
              {agents.map(agent => (
                <option key={agent} value={agent}>{agent}</option>
              ))}
            </select>
          </div>
          <button className="btn" onClick={loadBeliefs}>
            Apply Filters
          </button>
          <button className="btn" onClick={() => { setRunIdFilter(''); setAgentFilter(''); loadBeliefs(); }}>
            Clear
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '1rem', textAlign: 'center' }}>
          <div>
            <div style={{ fontSize: '2rem', fontWeight: 'bold', color: 'var(--primary)' }}>{beliefs.length}</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Total Beliefs</div>
          </div>
          <div>
            <div style={{ fontSize: '2rem', fontWeight: 'bold' }}>{Object.keys(beliefsByRun).length}</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Runs</div>
          </div>
          <div>
            <div style={{ fontSize: '2rem', fontWeight: 'bold' }}>{agents.length}</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Agents</div>
          </div>
          <div>
            <div style={{ fontSize: '2rem', fontWeight: 'bold', color: 'var(--success)' }}>
              {beliefs.filter(b => b.confidence >= 0.9).length}
            </div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>High Confidence</div>
          </div>
        </div>
      </div>

      {/* Beliefs List */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2>All Beliefs ({beliefs.length})</h2>
          <button className="btn" onClick={loadBeliefs}>↻ Refresh</button>
        </div>

        {beliefs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-secondary)' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>No beliefs found</div>
            <div>Beliefs are created when agents make claims during runs.</div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {beliefs.map((belief) => (
              <div key={belief.belief_id} style={{
                padding: '1.25rem',
                background: 'var(--bg-primary)',
                borderRadius: '8px',
                borderLeft: `4px solid ${belief.confidence >= 0.9 ? 'var(--success)' : belief.confidence >= 0.7 ? 'var(--warning)' : 'var(--text-secondary)'}`
              }}>
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                    <span style={{ fontWeight: 'bold', fontSize: '1.1rem' }}>{belief.agent_id}</span>
                    <span className="badge badge-pending">{Math.round(belief.confidence * 100)}% confidence</span>
                  </div>
                  <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                    {new Date(belief.created_at).toLocaleString()}
                  </div>
                </div>

                {/* Content */}
                <div style={{ marginBottom: '0.75rem', fontSize: '1rem', lineHeight: '1.5' }}>
                  {typeof belief.content === 'object' && belief.content !== null
                    ? (belief.content as Record<string, unknown>).claim as string || JSON.stringify(belief.content, null, 2)
                    : String(belief.content)
                  }
                </div>

                {/* Tags */}
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
                  {belief.topic_tags.map((tag) => (
                    <span key={tag} className="badge badge-pending">{tag}</span>
                  ))}
                </div>

                {/* Hashes */}
                <div style={{ display: 'flex', gap: '2rem', fontSize: '0.75rem', flexWrap: 'wrap' }}>
                  <div>
                    <span style={{ color: 'var(--text-secondary)' }}>Content: </span>
                    <span className="hash">{belief.content_hash.slice(0, 24)}...</span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-secondary)' }}>Parent: </span>
                    <span className="hash">{belief.parent_hash ? `${belief.parent_hash.slice(0, 24)}...` : '(root)'}</span>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-secondary)' }}>Run: </span>
                    <Link to={`/runs/${belief.run_id}`} className="link hash">{belief.run_id.slice(4, 20)}...</Link>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
