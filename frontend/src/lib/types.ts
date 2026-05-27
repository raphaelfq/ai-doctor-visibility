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

export interface CFMValidation {
  status: string
  name_found?: string | null
  specialty_found?: string | null
  situation?: string | null
}

export interface GeneratedPrompt {
  id: string
  text: string
  intent: string
  persona: string
  locale: string
}

export interface SimulatedResponse {
  prompt_id: string
  raw_text: string
  model: string
  citations: Citation[]
}

export interface Citation {
  title: string
  url: string
  snippet?: string | null
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
  presence: number
  quality: number
  position: number
  competitive: number
  overall: number
}

export interface ReportMetadata {
  model: string
  scored_at: string
  version: string
  duration_seconds?: number | null
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
