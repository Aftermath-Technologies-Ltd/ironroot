// Author: Bradley R. Kinnard
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { Strategy } from '../api/types'

export function Strategies() {
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadStrategies()
  }, [])

  async function loadStrategies() {
    try {
      setLoading(true)
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
      await api.promoteStrategy(strategyId)
      loadStrategies()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to promote strategy')
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
      <h1>Strategies</h1>

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Version</th>
              <th>Manifest Hash</th>
              <th>Gate Passed</th>
              <th>Promoted</th>
              <th>Scores</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {strategies.length === 0 ? (
              <tr>
                <td colSpan={7}>No strategies registered</td>
              </tr>
            ) : (
              strategies.map((strategy) => (
                <tr key={strategy.strategy_id}>
                  <td>{strategy.name}</td>
                  <td>{strategy.version}</td>
                  <td className="hash">{strategy.manifest_hash.slice(0, 12)}...</td>
                  <td>
                    <span className={`badge badge-${strategy.gate_passed ? 'success' : 'pending'}`}>
                      {strategy.gate_passed ? 'Yes' : 'No'}
                    </span>
                  </td>
                  <td>
                    <span className={`badge badge-${strategy.promoted ? 'success' : 'pending'}`}>
                      {strategy.promoted ? 'Yes' : 'No'}
                    </span>
                  </td>
                  <td>
                    {strategy.correctness_score !== null ? (
                      <span title="Correctness / Reproducibility / Efficiency / Safety">
                        {strategy.correctness_score?.toFixed(2)} /
                        {strategy.reproducibility_score?.toFixed(2)} /
                        {strategy.efficiency_score?.toFixed(2)} /
                        {strategy.safety_score?.toFixed(2)}
                      </span>
                    ) : (
                      <span className="hash">not scored</span>
                    )}
                  </td>
                  <td>
                    <button
                      className="btn"
                      onClick={() => handlePromote(strategy.strategy_id)}
                      disabled={!strategy.gate_passed || strategy.promoted}
                      title={!strategy.gate_passed ? 'Gate must pass before promotion' : undefined}
                    >
                      Promote
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
