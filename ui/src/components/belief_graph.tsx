// Author: Bradley R. Kinnard
import type { Belief } from '../api/types'

interface BeliefGraphProps {
  beliefs: Belief[]
}

export function BeliefGraph({ beliefs }: BeliefGraphProps) {
  // simple text-based visualization of belief chain
  const rootBeliefs = beliefs.filter((b) => !b.parent_hash)
  const childrenMap = new Map<string, Belief[]>()

  for (const belief of beliefs) {
    if (belief.parent_hash) {
      const children = childrenMap.get(belief.parent_hash) || []
      children.push(belief)
      childrenMap.set(belief.parent_hash, children)
    }
  }

  function renderBelief(belief: Belief, depth: number): JSX.Element {
    const children = childrenMap.get(belief.content_hash) || []
    const indent = '  '.repeat(depth)

    return (
      <div key={belief.belief_id}>
        <div style={{ fontFamily: 'monospace', fontSize: '0.875rem' }}>
          {indent}├─ <span className="hash">{belief.content_hash.slice(0, 12)}</span>
          {' '}
          <span style={{ color: 'var(--text-secondary)' }}>
            ({belief.agent_id}, {(belief.confidence * 100).toFixed(0)}%)
          </span>
        </div>
        {children.map((child) => renderBelief(child, depth + 1))}
      </div>
    )
  }

  if (beliefs.length === 0) {
    return <div>No beliefs to display</div>
  }

  return (
    <div className="card">
      <h3>Belief Chain</h3>
      <div style={{ whiteSpace: 'pre', overflowX: 'auto' }}>
        {rootBeliefs.map((belief) => renderBelief(belief, 0))}
      </div>
    </div>
  )
}
