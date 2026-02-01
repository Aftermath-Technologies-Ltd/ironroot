// Author: Bradley R. Kinnard
// Research Console - Main researcher-facing interface

import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { EvidenceArtifact, ResearchFinding, ResearchProgress, ResearchResults } from '../api/types'
import './research_console.css'

type ViewState = 'input' | 'progress' | 'results'

export function ResearchConsole() {
  const [viewState, setViewState] = useState<ViewState>('input')
  const [criteria, setCriteria] = useState('')
  const [researchId, setResearchId] = useState<string | null>(null)
  const [progress, setProgress] = useState<ResearchProgress | null>(null)
  const [results, setResults] = useState<ResearchResults | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [seed, setSeed] = useState<number | null>(null)
  const [expandedEvidence, setExpandedEvidence] = useState<Set<string>>(new Set())

  // Poll for progress
  useEffect(() => {
    if (viewState !== 'progress' || !researchId) return

    const interval = setInterval(async () => {
      try {
        const status = await api.getResearchStatus(researchId)
        setProgress(status)

        if (status.status === 'completed') {
          clearInterval(interval)
          const res = await api.getResearchResults(researchId)
          setResults(res)
          setViewState('results')
        } else if (status.status === 'failed') {
          clearInterval(interval)
          setError('Research failed. Please try again.')
          setViewState('input')
        }
      } catch (err) {
        // Results not ready yet, keep polling
      }
    }, 1000)

    return () => clearInterval(interval)
  }, [viewState, researchId])

  const handleSubmit = useCallback(async () => {
    if (!criteria.trim() || criteria.trim().length < 10) {
      setError('Please enter a more detailed research criteria (at least 10 characters)')
      return
    }

    setError(null)
    try {
      const response = await api.submitResearch({ criteria: criteria.trim(), seed })
      setResearchId(response.research_id)
      setProgress({
        status: 'pending',
        percent: 0,
        phase_description: 'Initializing research...',
        eta_seconds: response.estimated_time_seconds,
        phases_completed: [],
        current_phase: 'initialization',
        details: {},
      })
      setViewState('progress')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit research')
    }
  }, [criteria, seed])

  const handleReset = useCallback(() => {
    setCriteria('')
    setResearchId(null)
    setProgress(null)
    setResults(null)
    setError(null)
    setViewState('input')
    setExpandedEvidence(new Set())
  }, [])

  const toggleEvidence = useCallback((id: string) => {
    setExpandedEvidence(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }, [])

  return (
    <div className="research-console">
      <header className="console-header">
        <h1>IRONROOT Research Console</h1>
        <p className="subtitle">
          Autonomous research system with verifiable evidence
        </p>
      </header>

      {error && (
        <div className="error-banner">
          <span className="error-icon">⚠</span>
          {error}
          <button className="dismiss-btn" onClick={() => setError(null)}>×</button>
        </div>
      )}

      {viewState === 'input' && (
        <InputSection
          criteria={criteria}
          setCriteria={setCriteria}
          showAdvanced={showAdvanced}
          setShowAdvanced={setShowAdvanced}
          seed={seed}
          setSeed={setSeed}
          onSubmit={handleSubmit}
        />
      )}

      {viewState === 'progress' && progress && (
        <ProgressSection progress={progress} />
      )}

      {viewState === 'results' && results && (
        <ResultsSection
          results={results}
          expandedEvidence={expandedEvidence}
          toggleEvidence={toggleEvidence}
          onNewResearch={handleReset}
        />
      )}
    </div>
  )
}

function InputSection({
  criteria,
  setCriteria,
  showAdvanced,
  setShowAdvanced,
  seed,
  setSeed,
  onSubmit,
}: {
  criteria: string
  setCriteria: (c: string) => void
  showAdvanced: boolean
  setShowAdvanced: (v: boolean) => void
  seed: number | null
  setSeed: (s: number | null) => void
  onSubmit: () => void
}) {
  return (
    <section className="input-section">
      <div className="input-card">
        <label className="input-label">What would you like to research?</label>
        <textarea
          className="criteria-input"
          placeholder="Example: Test whether transfer learning improves prediction accuracy across different data domains without task-specific tuning..."
          value={criteria}
          onChange={(e) => setCriteria(e.target.value)}
          rows={5}
        />

        <div className="input-actions">
          <button
            className="advanced-toggle"
            onClick={() => setShowAdvanced(!showAdvanced)}
          >
            {showAdvanced ? '▼' : '▶'} Advanced Options
          </button>
          <button
            className="submit-btn"
            onClick={onSubmit}
            disabled={!criteria.trim() || criteria.trim().length < 10}
          >
            Submit Research
          </button>
        </div>

        {showAdvanced && (
          <div className="advanced-options">
            <label>
              Random Seed (for reproducibility):
              <input
                type="number"
                value={seed ?? ''}
                onChange={(e) => setSeed(e.target.value ? parseInt(e.target.value) : null)}
                placeholder="Leave blank for random"
              />
            </label>
          </div>
        )}
      </div>

      <div className="info-card">
        <h3>How it works</h3>
        <ol>
          <li><strong>Submit criteria</strong> — Describe what you want to research in plain English</li>
          <li><strong>Autonomous research</strong> — The system generates questions, forms hypotheses, gathers external data</li>
          <li><strong>Testing</strong> — Hypotheses are tested against real data with statistical rigor</li>
          <li><strong>Results</strong> — Get plain English findings backed by verifiable evidence</li>
        </ol>
      </div>
    </section>
  )
}

function ProgressSection({ progress }: { progress: ResearchProgress }) {
  const phases = [
    { key: 'parsing', label: 'Parsing' },
    { key: 'questions', label: 'Questions' },
    { key: 'hypotheses', label: 'Hypotheses' },
    { key: 'data', label: 'Data' },
    { key: 'testing', label: 'Testing' },
    { key: 'analyzing', label: 'Analyzing' },
  ]

  return (
    <section className="progress-section">
      <div className="progress-card">
        <h2>Research in Progress</h2>

        <div className="progress-bar-container">
          <div className="progress-bar" style={{ width: `${progress.percent}%` }}>
            <span className="progress-percent">{progress.percent}%</span>
          </div>
        </div>

        <p className="phase-description">{progress.phase_description}</p>

        {progress.eta_seconds !== null && progress.eta_seconds > 0 && (
          <p className="eta">
            Estimated time remaining: ~{Math.ceil(progress.eta_seconds / 60)} minute{progress.eta_seconds > 60 ? 's' : ''}
          </p>
        )}

        <div className="phase-indicators">
          {phases.map((phase) => {
            const isComplete = progress.phases_completed.includes(phase.key)
            const isCurrent = progress.current_phase === phase.key
            return (
              <div
                key={phase.key}
                className={`phase-indicator ${isComplete ? 'complete' : ''} ${isCurrent ? 'current' : ''}`}
              >
                <span className="phase-dot">
                  {isComplete ? '✓' : isCurrent ? '●' : '○'}
                </span>
                <span className="phase-label">{phase.label}</span>
              </div>
            )
          })}
        </div>

        {Object.keys(progress.details).length > 0 && (
          <div className="progress-details">
            {progress.details.questions_generated && (
              <span className="detail-badge">
                {progress.details.questions_generated} questions generated
              </span>
            )}
            {progress.details.hypotheses_formed && (
              <span className="detail-badge">
                {progress.details.hypotheses_formed} hypotheses formed
              </span>
            )}
            {progress.details.queries_made && (
              <span className="detail-badge">
                {progress.details.queries_made} data queries made
              </span>
            )}
          </div>
        )}

        <div className="working-animation">
          <span className="dot"></span>
          <span className="dot"></span>
          <span className="dot"></span>
        </div>
      </div>
    </section>
  )
}

function ResultsSection({
  results,
  expandedEvidence,
  toggleEvidence,
  onNewResearch,
}: {
  results: ResearchResults
  expandedEvidence: Set<string>
  toggleEvidence: (id: string) => void
  onNewResearch: () => void
}) {
  return (
    <section className="results-section">
      <div className="results-header">
        <h2>Research Complete</h2>
        <div className={`gate-badge ${results.gate_passed ? 'passed' : 'failed'}`}>
          {results.gate_passed ? '✓ Verified' : '⚠ Unverified'}
        </div>
      </div>

      <div className="original-criteria">
        <strong>Original Request:</strong> "{results.original_criteria}"
      </div>

      <div className="summary-card">
        <h3>Summary</h3>
        {results.summary.split('\n\n').map((paragraph, i) => (
          <p key={i}>{paragraph}</p>
        ))}
      </div>

      <div className="stats-row">
        <div className="stat">
          <span className="stat-value">{results.questions_generated}</span>
          <span className="stat-label">Questions</span>
        </div>
        <div className="stat">
          <span className="stat-value">{results.hypotheses_formed}</span>
          <span className="stat-label">Hypotheses</span>
        </div>
        <div className="stat">
          <span className="stat-value">{results.hypotheses_supported}</span>
          <span className="stat-label">Supported</span>
        </div>
        <div className="stat">
          <span className="stat-value">{results.experiments_run}</span>
          <span className="stat-label">Experiments</span>
        </div>
        <div className="stat">
          <span className="stat-value">{results.data_sources_queried}</span>
          <span className="stat-label">Data Sources</span>
        </div>
      </div>

      <div className="findings-card">
        <h3>Key Findings</h3>
        {results.findings.map((finding, i) => (
          <FindingItem key={i} finding={finding} />
        ))}
      </div>

      <div className="evidence-card">
        <h3>Evidence</h3>
        <p className="evidence-intro">
          All findings are backed by verifiable artifacts with cryptographic hashes.
        </p>
        {results.evidence.map((ev) => (
          <EvidenceItem
            key={ev.artifact_id}
            evidence={ev}
            expanded={expandedEvidence.has(ev.artifact_id)}
            onToggle={() => toggleEvidence(ev.artifact_id)}
          />
        ))}
      </div>

      <div className="results-actions">
        <button className="action-btn primary" onClick={onNewResearch}>
          New Research
        </button>
        <button className="action-btn" onClick={() => {
          const hashes = results.evidence.map(e => e.content_hash).join('\n')
          navigator.clipboard.writeText(hashes)
        }}>
          Copy Evidence Hashes
        </button>
      </div>

      <div className="timing-info">
        Completed in {results.duration_seconds.toFixed(1)} seconds
      </div>
    </section>
  )
}

function FindingItem({ finding }: { finding: ResearchFinding }) {
  const icon = finding.finding_type === 'success' ? '✓' :
               finding.finding_type === 'partial' ? '◐' : '✗'
  const className = `finding-item ${finding.finding_type}`

  return (
    <div className={className}>
      <span className="finding-icon">{icon}</span>
      <div className="finding-content">
        <p className="finding-summary">{finding.summary}</p>
        <p className="finding-context">{finding.context}</p>
      </div>
      {finding.value !== null && (
        <span className="finding-value">
          {typeof finding.value === 'number' && finding.value < 1
            ? `${(finding.value * 100).toFixed(0)}%`
            : finding.value}
        </span>
      )}
    </div>
  )
}

function EvidenceItem({
  evidence,
  expanded,
  onToggle,
}: {
  evidence: EvidenceArtifact
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <div className="evidence-item">
      <div className="evidence-header" onClick={onToggle}>
        <span className="evidence-toggle">{expanded ? '▼' : '▶'}</span>
        <span className="evidence-type">{evidence.artifact_type}</span>
        <span className="evidence-summary">{evidence.summary}</span>
        <span className="evidence-hash">{evidence.content_hash}</span>
      </div>
      {expanded && evidence.expandable_data && (
        <div className="evidence-details">
          <pre>{JSON.stringify(evidence.expandable_data, null, 2)}</pre>
        </div>
      )}
    </div>
  )
}
