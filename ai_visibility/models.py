"""Pydantic models for all pipeline stages.

Conventions (from PRACTICES §1):
- Pydantic v2 with Literal, Field(ge=, le=)
- X | None = None instead of Optional[X]
- All models are serialisable for report.json
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---------- Input ----------


class DoctorInput(BaseModel):
    name: str
    specialty: str
    city: str
    state: str | None = None
    neighborhood: str | None = None
    crm: str | None = None
    crm_state: str | None = None


# ---------- CFM Validation ----------


class CFMValidation(BaseModel):
    valid: bool | None = None
    registered_name: str | None = None
    status: str | None = None
    specialties: list[str] = []
    rqe_numbers: list[str] = []
    error: str | None = None


# ---------- Stage 1 — Prompt Generator ----------


PersonaType = Literal[
    "leigo_ansioso",
    "informado_específico",
    "urgência",
    "segunda_opinião",
    "pediátrico",
    "convênio_vs_particular",
    "estético_eletivo",
    "crônico_acompanhamento",
    "preventivo",
    "pediu_indicação",
]


class GeneratedPrompt(BaseModel):
    id: str = Field(description="Identifier like 'p1' .. 'p10'")
    text: str = Field(description="The patient prompt in PT-BR")
    persona: PersonaType
    intent_summary: str = Field(description="One-line summary of patient intent")


class GeneratedPrompts(BaseModel):
    """Wrapper for structured output from the generator stage."""

    prompts: list[GeneratedPrompt]


# ---------- Stage 2 — Search Simulator ----------


class Citation(BaseModel):
    url: str
    title: str


class SimulatedResponse(BaseModel):
    prompt_id: str
    raw_text: str
    doctors_named: list[str] = []
    citations: list[Citation] = []
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int


# ---------- Stage 3 — Judge ----------


CitationType = Literal[
    "mentioned_by_name",
    "mentioned_as_specialty",
    "competitor_in_place",
    "not_mentioned",
]


class Verdict(BaseModel):
    prompt_id: str
    citation_type: CitationType
    confidence: float = Field(ge=0.0, le=1.0)
    position: int | None = Field(
        None,
        ge=1,
        description="Rank in response (1 = first mentioned). Only set when mentioned_by_name.",
    )
    evidence_quote: str = Field(
        description="Literal excerpt from the simulated response justifying the verdict"
    )
    competitors_named: list[str] = []


# ---------- Stage 4 — Scorer ----------


class ScoreBreakdown(BaseModel):
    visibility: float = Field(ge=0, le=100)
    dominance: float = Field(ge=0, le=100)
    indirect_presence: float = Field(ge=0, le=100)
    overall: float = Field(ge=0, le=100)


# ---------- Report ----------


class ReportMetadata(BaseModel):
    generated_at: datetime
    model_generator: str
    model_simulator: str
    model_judge: str
    total_tokens_in: int
    total_tokens_out: int
    total_cost_usd: float
    seed: int


class Report(BaseModel):
    doctor: DoctorInput
    cfm_validation: CFMValidation | None = None
    prompts: list[GeneratedPrompt]
    responses: list[SimulatedResponse]
    verdicts: list[Verdict]
    score: ScoreBreakdown
    metadata: ReportMetadata


# ---------- Trace (observability) ----------


class TraceEntry(BaseModel):
    timestamp: datetime
    stage: str
    prompt_id: str | None = None
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    cost_usd: float
    status: Literal["success", "error", "timeout", "parse_error"]
    error: str | None = None
