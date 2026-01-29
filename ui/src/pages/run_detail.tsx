// Author: Bradley R. Kinnard
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Belief, GateStatus, RunStatus } from '../api/types'

export function RunDetail() {
  const { runId } = useParams<{ runId: string }>()
  const [run, setRun] = useState<RunStatus | null>(null)
  const [gateStatus, setGateStatus] = useState<GateStatus | null>(null)
  const [beliefs, setBeliefs] = useState<Belief[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    if (runId) {
      loadRunDetails(runId)
    }
  }, [runId])

  async function loadRunDetails(id: string) {
    try {
      setLoading(true)
      setError(null)
      const [runData, gateData, beliefsData] = await Promise.all([
        api.getRun(id),
        api.getGateStatus(id).catch(() => null),
        api.listBeliefs({ run_id: id }).catch(() => ({ beliefs: [] })),
      ])
      setRun(runData)
      setGateStatus(gateData)
      setBeliefs(beliefsData.beliefs)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load run')
    } finally {
      setLoading(false)
    }
  }

  async function handleStart() {
    if (!runId) return
    try {
      setActionError(null)
      await api.startRun(runId)
      loadRunDetails(runId)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to start run')
    }
  }

  async function handleStop() {
    if (!runId) return
    try {
      setActionError(null)
      await api.stopRun(runId)
      loadRunDetails(runId)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to stop run')
    }
  }

  async function handleExecuteGates() {
    if (!runId) return
    try {
      setActionError(null)
      await api.executeGates(runId)
      loadRunDetails(runId)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to execute gates')
    }
  }

  if (loading) {
    return <div className="card">Loading run details...</div>
  }

  if (error || !run) {
    return (
      <div className="card" style={{ borderColor: 'var(--danger)' }}>
        <h2 style={{ color: 'var(--danger)' }}>Error</h2>
        <p>{error || 'Run not found'}</p>
        <Link to="/runs" className="btn" style={{ marginTop: '1rem' }}>← Back to Runs</Link>
      </div>
    )
  }

  const totalSteps = run.steps_used + run.steps_remaining
  const totalTools = run.tool_calls_used + run.tool_calls_remaining
  const totalBeliefs = run.belief_writes_used + run.belief_writes_remaining
  const stepsPercent = totalSteps > 0 ? Math.round((run.steps_used / totalSteps) * 100) : 0
  const toolsPercent = totalTools > 0 ? Math.round((run.tool_calls_used / totalTools) * 100) : 0
  const beliefsPercent = totalBeliefs > 0 ? Math.round((run.belief_writes_used / totalBeliefs) * 100) : 0

  const phases = ['init', 'propose', 'build', 'test', 'verify', 'audit', 'decide', 'finalize']
  const currentPhaseIndex = phases.indexOf(run.phase)

  return (
    <div>
      <div style={{ marginBottom: '1rem' }}>
        <Link to="/runs" className="link">← Back to Runs</Link>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h1 style={{ margin: 0 }}>Run Details</h1>
        <span className={`badge badge-${
          run.status === 'completed' ? 'success' :
          run.status === 'failed' ? 'danger' :
          run.status === 'running' ? 'warning' : 'pending'
        }`} style={{ fontSize: '1rem', padding: '0.5rem 1rem' }}>
          {run.status.toUpperCase()}
        </span>
      </div>

      {/* Run Info */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
          <div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Run ID</div>
            <div className="hash" style={{ wordBreak: 'break-all' }}>{run.run_id}</div>
          </div>
          <div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Seed</div>
            <div style={{ fontFamily: 'monospace', fontSize: '1.25rem' }}>{run.seed}</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
              Same seed = reproducible results
            </div>
          </div>
          <div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Current Phase</div>
            <div style={{ fontWeight: 'bold', fontSize: '1.25rem' }}>{run.phase}</div>
          </div>
        </div>
      </div>

      {/* Phase Progress */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h2>Phase Progress</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.875rem' }}>
          A run progresses through these phases. Each phase involves different agents working together.
        </p>
        <div style={{ display: 'flex', gap: '0.25rem', marginBottom: '1rem' }}>
          {phases.map((phase, i) => (
            <div key={phase} style={{
              flex: 1,
              padding: '0.5rem',
              textAlign: 'center',
              background: i < currentPhaseIndex ? 'var(--success)' : i === currentPhaseIndex ? 'var(--primary)' : 'var(--bg-primary)',
              color: i <= currentPhaseIndex ? 'white' : 'var(--text-secondary)',
              borderRadius: i === 0 ? '8px 0 0 8px' : i === phases.length - 1 ? '0 8px 8px 0' : '0',
              fontSize: '0.75rem',
            }}>
              {phase}
            </div>
          ))}
        </div>
        <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
          <strong>Phases explained:</strong> init (setup) → propose (suggest changes) → build (implement) →
          test (write tests) → verify (try to break it) → audit (check integrity) → decide (accept/reject) → finalize
        </div>
      </div>

      {/* Budget Usage */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h2>Budget Usage</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.875rem' }}>
          Agents have limited resources. When budgets are exhausted, the run stops. Failed verifications cost budget permanently.
        </p>

        <div style={{ marginBottom: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
            <span>Steps</span>
            <span>{run.steps_used} / {totalSteps} ({stepsPercent}%)</span>
          </div>
          <div style={{ height: '12px', background: 'var(--bg-primary)', borderRadius: '6px', overflow: 'hidden' }}>
            <div style={{ width: `${stepsPercent}%`, height: '100%', background: stepsPercent > 80 ? 'var(--danger)' : 'var(--primary)' }} />
          </div>
        </div>

        <div style={{ marginBottom: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
            <span>Tool Calls</span>
            <span>{run.tool_calls_used} / {totalTools} ({toolsPercent}%)</span>
          </div>
          <div style={{ height: '12px', background: 'var(--bg-primary)', borderRadius: '6px', overflow: 'hidden' }}>
            <div style={{ width: `${toolsPercent}%`, height: '100%', background: toolsPercent > 80 ? 'var(--danger)' : 'var(--warning)' }} />
          </div>
        </div>

        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
            <span>Belief Writes</span>
            <span>{run.belief_writes_used} / {totalBeliefs} ({beliefsPercent}%)</span>
          </div>
          <div style={{ height: '12px', background: 'var(--bg-primary)', borderRadius: '6px', overflow: 'hidden' }}>
            <div style={{ width: `${beliefsPercent}%`, height: '100%', background: beliefsPercent > 80 ? 'var(--danger)' : 'var(--success)' }} />
          </div>
        </div>
      </div>

      {/* Gate Verification */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h2>Gate Verification</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.875rem' }}>
          Gates are verification checks that ensure the run's results are valid and reproducible.
          All gates must pass before results can be trusted.
        </p>

        {gateStatus ? (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
              <span className={`badge badge-${gateStatus.status === 'passed' ? 'success' : gateStatus.status === 'failed' ? 'danger' : 'pending'}`}
                    style={{ fontSize: '1rem', padding: '0.5rem 1rem' }}>
                {gateStatus.status === 'passed' ? '✓ ALL GATES PASSED' :
                 gateStatus.status === 'failed' ? '✗ GATES FAILED' :
                 'PENDING'}
              </span>
            </div>

            {gateStatus.results && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '1rem', marginBottom: '1rem' }}>
                {Object.entries((gateStatus.results as Record<string, Record<string, unknown>>).gates || {}).map(([gateName, result]) => (
                  <div key={gateName} style={{
                    padding: '1rem',
                    background: 'var(--bg-primary)',
                    borderRadius: '8px',
                    borderLeft: `4px solid ${(result as Record<string, unknown>).passed ? 'var(--success)' : 'var(--danger)'}`
                  }}>
                    <div style={{ fontWeight: 'bold', textTransform: 'capitalize' }}>{gateName}</div>
                    <div style={{ color: (result as Record<string, unknown>).passed ? 'var(--success)' : 'var(--danger)' }}>
                      {(result as Record<string, unknown>).passed ? '✓ Passed' : '✗ Failed'}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {gateStatus.artifact_id && (
              <div style={{ fontSize: '0.875rem' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Evidence: </span>
                <span className="hash">{gateStatus.artifact_id}</span>
              </div>
            )}

            {gateStatus.executed_at && (
              <div style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
                Executed: {new Date(gateStatus.executed_at).toLocaleString()}
              </div>
            )}
          </div>
        ) : (
          <div style={{ padding: '2rem', textAlign: 'center', background: 'var(--bg-primary)', borderRadius: '8px' }}>
            <div style={{ marginBottom: '0.5rem' }}>No gates executed yet</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
              Click "Execute Gates" below to run verification checks.
            </div>
          </div>
        )}
      </div>

      {/* Beliefs from this run */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h2>Beliefs from this Run ({beliefs.length})</h2>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.875rem' }}>
          Beliefs are immutable claims made by agents during the run. Each has a content hash for verification.
        </p>

        {beliefs.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
            No beliefs recorded in this run yet.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {beliefs.map((belief) => (
              <div key={belief.belief_id} style={{
                padding: '1rem',
                background: 'var(--bg-primary)',
                borderRadius: '8px',
                borderLeft: `4px solid ${belief.confidence >= 0.9 ? 'var(--success)' : belief.confidence >= 0.7 ? 'var(--warning)' : 'var(--text-secondary)'}`
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                  <span style={{ fontWeight: 'bold' }}>{belief.agent_id}</span>
                  <span style={{ fontSize: '0.875rem' }}>
                    {Math.round(belief.confidence * 100)}% confidence
                  </span>
                </div>
                <div style={{ marginBottom: '0.5rem' }}>
                  {typeof belief.content === 'object' && belief.content !== null
                    ? (belief.content as Record<string, unknown>).claim as string || JSON.stringify(belief.content)
                    : String(belief.content)
                  }
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                  {belief.topic_tags.map((tag) => (
                    <span key={tag} className="badge badge-pending">{tag}</span>
                  ))}
                  <span className="hash" style={{ marginLeft: 'auto', fontSize: '0.75rem' }}>
                    {belief.content_hash.slice(0, 20)}...
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="card">
        <h2>Actions</h2>
        {actionError && (
          <div style={{ marginBottom: '1rem', padding: '0.75rem', background: 'rgba(255,0,0,0.1)', borderRadius: '4px', color: 'var(--danger)' }}>
            {actionError}
          </div>
        )}
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <button
            className="btn btn-primary"
            onClick={handleStart}
            disabled={run.status !== 'pending'}
            title={run.status !== 'pending' ? 'Run can only be started when pending' : 'Start the research cycle'}
          >
            ▶ Start Run
          </button>
          <button
            className="btn"
            onClick={handleStop}
            disabled={run.status === 'stopped' || run.status === 'completed' || run.status === 'failed'}
          >
            ◼ Stop Run
          </button>
          <button
            className="btn"
            onClick={handleExecuteGates}
            title="Run verification gates on this run's results"
          >
            ✓ Execute Gates
          </button>
          <button
            className="btn"
            onClick={() => runId && loadRunDetails(runId)}
          >
            ↻ Refresh
          </button>
        </div>

        {run.failure_reason && (
          <div style={{ marginTop: '1rem', padding: '1rem', background: 'rgba(255,0,0,0.1)', borderRadius: '8px', borderLeft: '4px solid var(--danger)' }}>
            <div style={{ fontWeight: 'bold', color: 'var(--danger)', marginBottom: '0.5rem' }}>Failure Reason</div>
            <div>{run.failure_reason}</div>
          </div>
        )}
      </div>
    </div>
  )
}
