// Author: Bradley R. Kinnard

interface GateStatusBadgeProps {
  status: 'pending' | 'passed' | 'failed'
}

export function GateStatusBadge({ status }: GateStatusBadgeProps) {
  const className = status === 'passed' ? 'badge-success' : status === 'failed' ? 'badge-danger' : 'badge-pending'

  return (
    <span className={`badge ${className}`}>
      {status}
    </span>
  )
}
