// Author: Bradley R. Kinnard
import { Link } from 'react-router-dom'
import type { GateStatus, RunStatus } from '../api/types'
import { GateStatusBadge } from './gate_status'

interface RunTableProps {
  runs: RunStatus[]
  gateStatuses: Record<string, GateStatus>
}

export function RunTable({ runs, gateStatuses }: RunTableProps) {
  if (runs.length === 0) {
    return <div>No runs found</div>
  }

  return (
    <table className="table">
      <thead>
        <tr>
          <th>Run ID</th>
          <th>Status</th>
          <th>Phase</th>
          <th>Seed</th>
          <th>Steps</th>
          <th>Gate Status</th>
          <th>Evidence</th>
        </tr>
      </thead>
      <tbody>
        {runs.map((run) => {
          const gate = gateStatuses[run.run_id]
          return (
            <tr key={run.run_id}>
              <td>
                <Link to={`/runs/${run.run_id}`} className="link">
                  {run.run_id.slice(0, 16)}...
                </Link>
              </td>
              <td>
                <span className={`badge badge-${run.status === 'completed' ? 'success' : run.status === 'failed' ? 'danger' : 'pending'}`}>
                  {run.status}
                </span>
              </td>
              <td>{run.phase}</td>
              <td className="hash">{run.seed}</td>
              <td>{run.steps_used} / {run.steps_used + run.steps_remaining}</td>
              <td>
                {gate ? (
                  <GateStatusBadge status={gate.status} />
                ) : (
                  <span className="badge badge-pending">pending</span>
                )}
              </td>
              <td>
                {gate?.artifact_id ? (
                  <a
                    href={`/api/v1/artifacts/${gate.artifact_id}`}
                    className="link hash evidence-link"
                  >
                    {gate.artifact_id.slice(0, 12)}...
                  </a>
                ) : (
                  <span className="hash">-</span>
                )}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
