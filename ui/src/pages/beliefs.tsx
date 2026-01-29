// Author: Bradley R. Kinnard
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Belief } from '../api/types'

export function Beliefs() {
  const [beliefs, setBeliefs] = useState<Belief[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [runIdFilter, setRunIdFilter] = useState('')

  useEffect(() => {
    loadBeliefs()
  }, [])

  async function loadBeliefs() {
    try {
      setLoading(true)
      const params = runIdFilter ? { run_id: runIdFilter } : undefined
      const response = await api.listBeliefs(params)
      setBeliefs(response.beliefs)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load beliefs')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <div className="card">Loading...</div>
  }

  if (error) {
    return <div className="card">Error: {error}</div>
  }

  return (
    <div>
      <h1>Beliefs</h1>

      <div className="card">
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
          <input
            type="text"
            placeholder="Filter by run ID"
            value={runIdFilter}
            onChange={(e) => setRunIdFilter(e.target.value)}
            style={{
              padding: '0.5rem',
              background: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              borderRadius: '4px',
              color: 'var(--text-primary)',
            }}
          />
          <button className="btn" onClick={loadBeliefs}>
            Filter
          </button>
        </div>

        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Run</th>
              <th>Agent</th>
              <th>Content Hash</th>
              <th>Parent Hash</th>
              <th>Confidence</th>
              <th>Topics</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {beliefs.length === 0 ? (
              <tr>
                <td colSpan={8}>No beliefs found</td>
              </tr>
            ) : (
              beliefs.map((belief) => (
                <tr key={belief.belief_id}>
                  <td className="hash">{belief.belief_id.slice(0, 12)}...</td>
                  <td className="hash">{belief.run_id.slice(0, 12)}...</td>
                  <td>{belief.agent_id}</td>
                  <td>
                    <span className="hash evidence-link">
                      {belief.content_hash.slice(0, 12)}...
                    </span>
                  </td>
                  <td className="hash">
                    {belief.parent_hash ? `${belief.parent_hash.slice(0, 12)}...` : 'root'}
                  </td>
                  <td>{(belief.confidence * 100).toFixed(0)}%</td>
                  <td>
                    {belief.topic_tags.map((tag) => (
                      <span key={tag} className="badge badge-pending" style={{ marginRight: '0.25rem' }}>
                        {tag}
                      </span>
                    ))}
                  </td>
                  <td>{new Date(belief.created_at).toLocaleString()}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
