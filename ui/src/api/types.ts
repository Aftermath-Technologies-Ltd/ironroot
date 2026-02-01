// Author: Bradley R. Kinnard
// API types matching backend OpenAPI schema

export interface RunStatus {
  run_id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'stopped'
  phase: string
  seed: number
  steps_used: number
  steps_remaining: number
  tool_calls_used: number
  tool_calls_remaining: number
  belief_writes_used: number
  belief_writes_remaining: number
  gate_status: 'pending' | 'passed' | 'failed' | null
  failure_reason: string | null
}

export interface RunListResponse {
  runs: RunStatus[]
  offset: number
  limit: number
  total: number
}

export interface GateStatus {
  run_id: string
  status: 'pending' | 'passed' | 'failed'
  gate_id?: string
  artifact_id?: string
  results?: Record<string, unknown>
  executed_at?: string
}

export interface Strategy {
  strategy_id: string
  name: string
  version: string
  manifest_hash: string
  gate_passed: boolean
  promoted: boolean
  correctness_score: number | null
  reproducibility_score: number | null
  efficiency_score: number | null
  safety_score: number | null
}

export interface StrategyListResponse {
  strategies: Strategy[]
  offset: number
  limit: number
  total: number
}

export interface Belief {
  belief_id: string
  run_id: string
  agent_id: string
  content_hash: string
  parent_hash: string | null
  content: Record<string, unknown>
  confidence: number
  topic_tags: string[]
  evidence_ids: string[]
  created_at: string
}

export interface BeliefListResponse {
  beliefs: Belief[]
  offset: number
  limit: number
  total: number
}

export interface Artifact {
  id: string
  content_hash: string
  artifact_type: string
  size_bytes: number
  created_by: string
  run_id: string | null
  filename: string | null
  created_at: string
}

// Research Console types
export interface ResearchProgress {
  status: string
  percent: number
  phase_description: string
  eta_seconds: number | null
  phases_completed: string[]
  current_phase: string
  details: Record<string, unknown>
}

export interface ResearchFinding {
  finding_type: 'success' | 'partial' | 'negative'
  summary: string
  metric_name: string | null
  value: number | null
  context: string
}

export interface EvidenceArtifact {
  artifact_id: string
  artifact_type: string
  content_hash: string
  summary: string
  created_at: string
  expandable_data: Record<string, unknown> | null
}

export interface ResearchResults {
  research_id: string
  original_criteria: string
  summary: string
  findings: ResearchFinding[]
  evidence: EvidenceArtifact[]
  questions_generated: number
  hypotheses_formed: number
  hypotheses_supported: number
  hypotheses_falsified: number
  hypotheses_revised: number
  experiments_run: number
  data_sources_queried: number
  started_at: string
  completed_at: string
  duration_seconds: number
  gate_passed: boolean
}

export interface SubmitResearchResponse {
  research_id: string
  status: string
  message: string
  estimated_time_seconds: number
}
