// Author: Bradley R. Kinnard
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { GateStatus, RunStatus } from '../api/types'

export function Runs() {
  const [runs, setRuns] = useState<RunStatus[]>([])
  const [gateStatuses, setGateStatuses] = useState<Record<string, GateStatus>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [seedInput, setSeedInput] = useState('')
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  useEffect(() => {
    loadRuns()
  }, [])

  async function loadRuns() {
    try {
      setLoading(true)
      setError(null)
      const response = await api.listRuns({ limit: 100 })
      setRuns(response.runs)

      const statuses: Record<string, GateStatus> = {}
      await Promise.all(
        response.runs.map(async (run) => {
          try {
            statuses[run.run_id] = await api.getGateStatus(run.run_id)
          } catch {
            // no gate yet
          }
        })
      )
      setGateStatuses(statuses)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load runs')
    } finally {
      setLoading(false)
    }
  }

  async function handleCreateRun() {
    try {
      setCreating(true)
      setError(null)
      const seed = seedInput ? parseInt(seedInput, 10) : Math.floor(Math.random() * 1000000)
      if (isNaN(seed)) {
        setError('Seed must be a number')
        return
      }
      await api.createRun({ seed })
      setSeedInput('')
      await loadRuns()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create run')
    } finally {
      setCreating(false)
    }
  }

  async function handleStartRun(runId: string) {
    try {
      setActionLoading(runId)
      setError(null)
      await api.startRun(runId)
      await loadRuns()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start run')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleStopRun(runId: string) {
    try {
      setActionLoading(runId)
      setError(null)
      await api.stopRun(runId)
      await loadRuns()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop run')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleExecuteGates(runId: string) {
    try {
      setActionLoading(runId)
      setError(null)
      await api.executeGates(runId)
      await loadRuns()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to execute gates')
    } finally {
      setActionLoading(null)
    }
  }

  if (loading) {
    return <div className="card">Loading runs...</div>
  }

  return (
    <div>
      <h1>Research Runs</h1>

      {/* Explanation */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h2>What is a Run?</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>
          A <strong>run</strong> is a complete research cycle where agents work together to propose,
          build, test, and verify changes. Each run has:
        </p>
        <ul style={{ color: 'var(--text-secondary)', marginLeft: '1.5rem', lineHeight: '1.8' }}>
          <li><strong>Seed</strong> — A number that makes the run reproducible. Same seed = same results.</li>
          <li><strong>Budgets</strong> — Limits on steps, tool calls, and memory writes. Agents stop when exhausted.</li>
          <li><strong>Phases</strong> — init → propose → build → test → verify → audit → decide</li>
          <li><strong>Gates</strong> — Verification checks that must pass for results to be trusted.</li>
        </ul>
      </div>

      {/* Create Run */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h2>Create New Run</h2>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
              Seed (optional — leave empty for random)
            </label>
            <input
              type="number"
              placeholder="e.g. 42"
              value={seedInput}
              onChange={(e) => setSeedInput(e.target.value)}
              style={{
                padding: '0.5rem 1rem',
                background: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                borderRadius: '4px',
                color: 'var(--text-primary)',
                width: '150px',
              }}
            />
          </div>
          <button
            className="btn btn-primary"
            onClick={handleCreateRun}
            disabled={creating}
          >
            {creating ? 'Creating...' : 'Create Run'}
          </button>
        </div>
        {error && (
          <div style={{ marginTop: '1rem', color: 'var(--danger)' }}>{error}</div>
        )}
      </div>

      {/* Runs List */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h2>All Runs ({runs.length})</h2>
          <button className="btn" onClick={loadRuns}>↻ Refresh</button>
        </div>

        {runs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-secondary)' }}>
            <div style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>No runs yet</div>
            <div>Create your first run above to start a research cycle.</div>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Status</th>
                <th>Phase</th>
                <th>Seed</th>
                <th>Steps Used</th>
                <th>Tool Calls</th>
                <th>Beliefs</th>
                <th>Gate</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const gate = gateStatuses[run.run_id]
                const totalSteps = run.steps_used + run.steps_remaining
                const totalTools = run.tool_calls_used + run.tool_calls_remaining
                const totalBeliefs = run.belief_writes_used + run.belief_writes_remaining

                return (
                  <tr key={run.run_id}>
                    <td>
                      <Link to={`/runs/${run.run_id}`} className="link hash">
                        {run.run_id.slice(4, 20)}...
                      </Link>
                    </td>
                    <td>
                      <span className={`badge badge-${
                        run.status === 'completed' ? 'success' :
                        run.status === 'failed' ? 'danger' :
                        run.status === 'running' ? 'warning' : 'pending'
                      }`}>
                        {run.status}
                      </span>
                    </td>
                    <td>{run.phase}</td>
                    <td className="hash">{run.seed}</td>
                    <td>{run.steps_used} / {totalSteps}</td>
                    <td>{run.tool_calls_used} / {totalTools}</td>
                    <td>{run.belief_writes_used} / {totalBeliefs}</td>
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
                      <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                        {run.status === 'pending' && (
                          <button
                            className="btn btn-primary"
                            style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                            onClick={() => handleStartRun(run.run_id)}
                            disabled={actionLoading === run.run_id}
                          >
                            {actionLoading === run.run_id ? '...' : '▶ Start'}
                          </button>
                        )}
                        {run.status === 'running' && (
                          <button
                            className="btn"
                            style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                            onClick={() => handleStopRun(run.run_id)}
                            disabled={actionLoading === run.run_id}
                          >
                            {actionLoading === run.run_id ? '...' : '◼ Stop'}
                          </button>
                        )}
                        {(run.status === 'running' || run.status === 'completed') && (
                          <button
                            className="btn"
                            style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                            onClick={() => handleExecuteGates(run.run_id)}
                            disabled={actionLoading === run.run_id}
                          >
                            {actionLoading === run.run_id ? '...' : '✓ Gates'}
                          </button>
                        )}
                        <Link
                          to={`/runs/${run.run_id}`}
                          className="btn"
                          style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                        >
                          Details
                        </Link>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
