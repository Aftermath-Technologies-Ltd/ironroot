// Author: Bradley R. Kinnard

interface DiffViewProps {
  before: string
  after: string
  filename?: string
}

export function DiffView({ before, after, filename }: DiffViewProps) {
  const beforeLines = before.split('\n')
  const afterLines = after.split('\n')

  return (
    <div className="card">
      {filename && <h3>{filename}</h3>}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
        <div>
          <h4 style={{ color: 'var(--danger)' }}>Before</h4>
          <pre style={{
            background: 'var(--bg-primary)',
            padding: '1rem',
            borderRadius: '4px',
            overflow: 'auto',
            fontSize: '0.875rem',
          }}>
            {beforeLines.map((line, i) => (
              <div key={i} style={{ color: 'var(--text-secondary)' }}>
                <span style={{ color: 'var(--text-secondary)', marginRight: '1rem' }}>{i + 1}</span>
                {line}
              </div>
            ))}
          </pre>
        </div>
        <div>
          <h4 style={{ color: 'var(--success)' }}>After</h4>
          <pre style={{
            background: 'var(--bg-primary)',
            padding: '1rem',
            borderRadius: '4px',
            overflow: 'auto',
            fontSize: '0.875rem',
          }}>
            {afterLines.map((line, i) => (
              <div key={i} style={{ color: 'var(--text-secondary)' }}>
                <span style={{ color: 'var(--text-secondary)', marginRight: '1rem' }}>{i + 1}</span>
                {line}
              </div>
            ))}
          </pre>
        </div>
      </div>
    </div>
  )
}
