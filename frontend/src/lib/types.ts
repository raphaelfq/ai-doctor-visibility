// ---------------------------------------------------------------------------
// Domain types matching the FastAPI backend JSON API
// ---------------------------------------------------------------------------

export interface Doctor {
  id: string
  name: string
  specialty: string
  city: string
  state?: string | null
  neighborhood?: string | null
  crm?: string | null
  crm_state?: string | null
  created_at: string
  run_count: number
  latest_score?: number | null
}

export interface DoctorDetail extends Doctor {
  runs: RunSummary[]
}

export type RunStatus = "pending" | "running" | "completed" | "failed"

export interface RunSummary {
  id: string
  status: RunStatus
  score?: number | null
  progress?: string | null
  created_at: string
  completed_at?: string | null
}

/** Returned by GET /api/runs — includes doctor info for list display */
export interface RunListItem extends RunSummary {
  doctor_id: string
  doctor_name: string
  specialty: string
  city: string
}

export interface RunDetail extends RunSummary {
  doctor_id: string
  doctor_name: string
  specialty: string
  city: string
  state?: string | null
  neighborhood?: string | null
  crm?: string | null
  crm_state?: string | null
  error?: string | null
  report?: Report | null
  recommendations?: string[] | null
  benchmark?: number | null
}

// ---------------------------------------------------------------------------
// Report sub-types
// ---------------------------------------------------------------------------

export interface CFMValidation {
  valid: boolean | null
  registered_name?: string | null
  status?: string | null
  specialties: string[]
  rqe_numbers: string[]
  error?: string | null
}

export interface Report {
  doctor: ReportDoctor
  cfm_validation?: CFMValidation | null
  prompts: GeneratedPrompt[]
  responses: SimulatedResponse[]
  verdicts: Verdict[]
  score: ScoreBreakdown
  metadata: ReportMetadata
}

export interface ReportDoctor {
  name: string
  specialty: string
  city: string
  state?: string | null
  neighborhood?: string | null
  crm?: string | null
  crm_state?: string | null
}

export interface GeneratedPrompt {
  id: string
  text: string
  persona: string
  intent_summary: string
}

export interface SimulatedResponse {
  prompt_id: string
  raw_text: string
  doctors_named: string[]
  citations: Citation[]
  model: string
  tokens_in: number
  tokens_out: number
  latency_ms: number
}

export interface Citation {
  title: string
  url: string
}

export type CitationType =
  | "mentioned_by_name"
  | "mentioned_as_specialty"
  | "competitor_in_place"
  | "not_mentioned"

export interface Verdict {
  prompt_id: string
  citation_type: CitationType
  confidence: number
  position?: number | null
  evidence_quote: string
  competitors_named: string[]
}

export interface ScoreBreakdown {
  visibility: number
  dominance: number
  indirect_presence: number
  overall: number
}

export interface ReportMetadata {
  generated_at: string
  model_generator: string
  model_simulator: string
  model_judge: string
  total_tokens_in: number
  total_tokens_out: number
  total_cost_usd: number
  seed: number
}

// ---------------------------------------------------------------------------
// API request payloads
// ---------------------------------------------------------------------------

export interface CreateDoctorPayload {
  name: string
  specialty: string
  city: string
  state?: string
  neighborhood?: string
  crm?: string
  crm_state?: string
}

export interface CreateRunPayload {
  doctor_id: string
}

export interface CreateRunResponse {
  run_id: string
  status: RunStatus
}
