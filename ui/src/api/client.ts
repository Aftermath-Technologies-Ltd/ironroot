// Author: Bradley R. Kinnard
// API client for IRONROOT backend

const BASE_URL = '/api/v1'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(error.detail || `HTTP ${response.status}`)
  }

  return response.json()
}

export const api = {
  // runs
  listRuns: (params?: { status?: string; offset?: number; limit?: number }) => {
    const query = new URLSearchParams()
    if (params?.status) query.set('status', params.status)
    if (params?.offset) query.set('offset', String(params.offset))
    if (params?.limit) query.set('limit', String(params.limit))
    const qs = query.toString()
    return request<import('./types').RunListResponse>(`/runs${qs ? `?${qs}` : ''}`)
  },

  getRun: (runId: string) =>
    request<import('./types').RunStatus>(`/runs/${runId}`),

  createRun: (config: { seed: number }) =>
    request<{ run_id: string; request_id: string }>('/runs', {
      method: 'POST',
      body: JSON.stringify(config),
    }),

  startRun: (runId: string) =>
    request<{ run_id: string; status: string }>(`/runs/${runId}/start`, {
      method: 'POST',
    }),

  stopRun: (runId: string) =>
    request<{ run_id: string; status: string }>(`/runs/${runId}/stop`, {
      method: 'POST',
    }),

  getGateStatus: (runId: string) =>
    request<import('./types').GateStatus>(`/runs/${runId}/gates/status`),

  executeGates: (runId: string) =>
    request<{ run_id: string; gate_id: string; status: string }>(`/runs/${runId}/gates/execute`, {
      method: 'POST',
    }),

  // strategies
  listStrategies: (params?: { name?: string; promoted_only?: boolean }) => {
    const query = new URLSearchParams()
    if (params?.name) query.set('name', params.name)
    if (params?.promoted_only) query.set('promoted_only', 'true')
    const qs = query.toString()
    return request<import('./types').StrategyListResponse>(`/strategies${qs ? `?${qs}` : ''}`)
  },

  getStrategy: (strategyId: string) =>
    request<import('./types').Strategy>(`/strategies/${strategyId}`),

  promoteStrategy: (strategyId: string) =>
    request<{ strategy_id: string; status: string }>(`/strategies/${strategyId}/promote`, {
      method: 'POST',
    }),

  // beliefs
  listBeliefs: (params?: { run_id?: string; agent_id?: string }) => {
    const query = new URLSearchParams()
    if (params?.run_id) query.set('run_id', params.run_id)
    if (params?.agent_id) query.set('agent_id', params.agent_id)
    const qs = query.toString()
    return request<import('./types').BeliefListResponse>(`/beliefs${qs ? `?${qs}` : ''}`)
  },

  getBelief: (beliefId: string) =>
    request<import('./types').Belief>(`/beliefs/${beliefId}`),

  // artifacts
  getArtifact: (artifactId: string) =>
    request<import('./types').Artifact>(`/artifacts/${artifactId}`),

  // health
  getHealth: () =>
    request<{ status: string; db: string; redis: string; artifacts: string }>('/health'),

  // research console
  submitResearch: (params: { criteria: string; seed?: number | null }) =>
    request<import('./types').SubmitResearchResponse>('/research/submit', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  getResearchStatus: (researchId: string) =>
    request<import('./types').ResearchProgress>(`/research/${researchId}/status`),

  getResearchResults: (researchId: string) =>
    request<import('./types').ResearchResults>(`/research/${researchId}/results`),
}
