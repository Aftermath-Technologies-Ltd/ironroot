// Author: Bradley R. Kinnard
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { GateStatus, RunStatus } from '../api/types'
import { GateStatusBadge } from '../components/gate_status'

export function RunDetail() {
  const { runId } = useParams<{ runId: string }>()
  const [run, setRun] = useState<RunStatus | null>(null)
  const [gateStatus, setGateStatus] = useState<GateStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (runId) {
      loadRunDetails(runId)
    }
  }, [runId])

  async function loadRunDetails(id: string) {
    try {
      setLoading(true)
      const [runData, gateData] = await Promise.all([
        api.getRun(id),
        api.getGateStatus(id).catch(() => null),
      ])
      setRun(runData)
      setGateStatus(gateData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load run')
    } finally {
      setLoading(false)
    }
  }

  async function handleStart() {
    if (!runId) return
    try {
      await api.startRun(runId)
      loadRunDetails(runId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start run')
    }
  }

  async function handleStop() {
    if (!runId) return
    try {
      await api.stopRun(runId)
      loadRunDetails(runId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop run')
    }
  }

  async function handleExecuteGates() {
    if (!runId) return
    try {
      await api.executeGates(runId)
      loadRunDetails(runId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to execute gates')
    }
  }

  if (loading) {
    return <div className="card">Loading...</div>
  }

  if (error || !run) {
    return <div className="card">Error: {error || 'Run not found'}</div>
  }

  return (
    <div>
      <div style={{ marginBottom: '1rem' }}>
        <Link to="/" className="link">← Back to Dashboard</Link>
      </div>

      <h1>Run: {run.run_id}</h1>

      <div className="card">
        <h2>Status</h2>
        <table className="table">
          <tbody>
            <tr>
              <th>Status</th>
              <td>
                <span className={`badge badge-${run.status === 'completed' ? 'success' : run.status === 'failed' ? 'danger' : 'pending'}`}>
                  {run.status}
                </span>
              </td>
            </tr>
            <tr>
              <th>Phase</th>
              <td>{run.phase}</td>
            </tr>
            <tr>
              <th>Seed</th>
              <td className="hash">{run.seed}</td>
            </tr>
            <tr>
              <th>Steps</th>
              <td>{run.steps_used} / {run.steps_used + run.steps_remaining}</td>
            </tr>
            <tr>
              <th>Tool Calls</th>
              <td>{run.tool_calls_used} / {run.tool_calls_used + run.tool_calls_remaining}</td>
            </tr>
            <tr>
              <th>Belief Writes</th>
              <td>{run.belief_writes_used} / {run.belief_writes_used + run.belief_writes_remaining}</td>
            </tr>
            {run.failure_reason && (
              <tr>
                <th>Failure</th>
                <td style={{ color: 'var(--danger)' }}>{run.failure_reason}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>Gate Status</h2>
        {gateStatus ? (
          <div>
            <GateStatusBadge status={gateStatus.status} />
            {gateStatus.artifact_id && (
              <div style={{ marginTop: '0.5rem' }}>
                <span className="evidence-link">
                  <a href={`/api/v1/artifacts/${gateStatus.artifact_id}`} className="link hash">
                    {gateStatus.artifact_id}
                  </a>
                </span>
              </div>
            )}
            {gateStatus.executed_at && (
              <div style={{ marginTop: '0.5rem', color: 'var(--text-secondary)' }}>
                Executed: {new Date(gateStatus.executed_at).toLocaleString()}
              </div>
            )}
          </div>
        ) : (
          <div>No gates executed yet</div>
        )}
      </div>

      <div className="card">
        <h2>Actions</h2>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className="btn btn-primary" onClick={handleStart} disabled={run.status !== 'pending'}>
            Start
          </button>
          <button className="btn" onClick={handleStop} disabled={run.status === 'stopped' || run.status === 'completed'}>
            Stop
          </button>
          <button className="btn" onClick={handleExecuteGates}>
            Execute Gates
          </button>
          <button className="btn" onClick={() => runId && loadRunDetails(runId)}>
            Refresh
          </button>
        </div>
      </div>
    </div>
  )
}
