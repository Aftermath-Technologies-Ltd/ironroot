// Author: Bradley R. Kinnard
import { useEffect, useState } from 'react'
import { api } from '../api/client'

interface HealthStatus {
  status: string
  db: string
  redis: string
  artifacts: string
}

export function Tests() {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadHealth()
  }, [])

  async function loadHealth() {
    try {
      setLoading(true)
      const data = await api.getHealth()
      setHealth(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load health')
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
      <h1>Tests & System Status</h1>

      <div className="card">
        <h2>System Health</h2>
        {health && (
          <table className="table">
            <tbody>
              <tr>
                <th>Overall</th>
                <td>
                  <span className={`badge badge-${health.status === 'healthy' ? 'success' : 'danger'}`}>
                    {health.status}
                  </span>
                </td>
              </tr>
              <tr>
                <th>Database</th>
                <td>
                  <span className={`badge badge-${health.db === 'ok' ? 'success' : 'danger'}`}>
                    {health.db}
                  </span>
                </td>
              </tr>
              <tr>
                <th>Redis</th>
                <td>
                  <span className={`badge badge-${health.redis === 'ok' ? 'success' : 'warning'}`}>
                    {health.redis}
                  </span>
                </td>
              </tr>
              <tr>
                <th>Artifact Store</th>
                <td>
                  <span className={`badge badge-${health.artifacts === 'ok' ? 'success' : 'danger'}`}>
                    {health.artifacts}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h2>Test Suites</h2>
        <p style={{ color: 'var(--text-secondary)' }}>
          Test results are displayed here after gate execution. Each test run produces artifacts
          with content hashes that can be verified independently.
        </p>
        <button className="btn" onClick={loadHealth}>
          Refresh Status
        </button>
      </div>

      <div className="card">
        <h2>Coverage & Static Analysis</h2>
        <p style={{ color: 'var(--text-secondary)' }}>
          Coverage reports and static analysis results are stored as artifacts.
          See the CI pipeline for the latest quality gate status.
        </p>
      </div>
    </div>
  )
}
