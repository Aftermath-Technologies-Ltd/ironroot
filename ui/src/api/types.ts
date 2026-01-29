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
  id: string
  run_id: string
  agent_id: string
  content_hash: string
  parent_hash: string | null
  content: Record<string, unknown>
  confidence: number
  topic_tags: string[]
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
