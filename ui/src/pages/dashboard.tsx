// Author: Bradley R. Kinnard
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { GateStatus, RunStatus } from '../api/types'
import { RunTable } from '../components/run_table'

export function Dashboard() {
  const [runs, setRuns] = useState<RunStatus[]>([])
  const [gateStatuses, setGateStatuses] = useState<Record<string, GateStatus>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadRuns()
  }, [])

  async function loadRuns() {
    try {
      setLoading(true)
      const response = await api.listRuns({ limit: 50 })
      setRuns(response.runs)

      // load gate status for each run
      const statuses: Record<string, GateStatus> = {}
      await Promise.all(
        response.runs.map(async (run) => {
          try {
            statuses[run.run_id] = await api.getGateStatus(run.run_id)
          } catch {
            // gate status may not exist yet
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
      const seed = Math.floor(Math.random() * 1000000)
      await api.createRun({ seed })
      loadRuns()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create run')
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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h1>Dashboard</h1>
        <button className="btn btn-primary" onClick={handleCreateRun}>
          Create Run
        </button>
      </div>

      <div className="card">
        <h2>Active Runs</h2>
        <RunTable runs={runs} gateStatuses={gateStatuses} />
      </div>

      <div className="card">
        <h2>Quick Actions</h2>
        <button className="btn" onClick={loadRuns}>
          Refresh
        </button>
      </div>
    </div>
  )
}
