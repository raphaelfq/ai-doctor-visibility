"""Integration test — full pipeline end-to-end with mocked LLM calls.

Proves all 4 stages chain correctly (generator -> simulator -> judge -> scorer)
without making real API calls.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from ai_visibility.models import (
    CFMValidation,
    DoctorInput,
    GeneratedPrompt,
    GeneratedPrompts,
    Report,
)
from ai_visibility.pipeline import run_pipeline
from ai_visibility.stages.judge import DecomposedEvaluation

# ---------------------------------------------------------------------------
# Personas (all 10 required by the generator)
# ---------------------------------------------------------------------------

PERSONAS = [
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

# ---------------------------------------------------------------------------
# Canned prompts — Stage 1 (generator)
# ---------------------------------------------------------------------------

CANNED_PROMPTS = GeneratedPrompts(
    prompts=[
        GeneratedPrompt(
            id=f"p{i+1}",
            text=f"Prompt simulado de paciente com persona {persona}",
            persona=persona,
            intent_summary=f"Resumo da intenção para {persona}",
        )
        for i, persona in enumerate(PERSONAS)
    ]
)

# ---------------------------------------------------------------------------
# Canned judge evaluations — Stage 3
# Realistic mix: 3 mentioned_by_name, 3 competitor_in_place, 2 mentioned_as_specialty, 2 not_mentioned
# ---------------------------------------------------------------------------

JUDGE_EVALS: dict[str, DecomposedEvaluation] = {
    # mentioned_by_name (p1, p2, p3)
    "p1": DecomposedEvaluation(
        name_found=True,
        name_position=1,
        competitors_found=["Dra. Maria Silva"],
        specialty_recommended=True,
        evidence_quote="Dr. Teste é um excelente dermatologista em Campinas",
    ),
    "p2": DecomposedEvaluation(
        name_found=True,
        name_position=2,
        competitors_found=["Dr. João Oliveira", "Dra. Maria Silva"],
        specialty_recommended=True,
        evidence_quote="Recomendo Dr. João Oliveira e também o Dr. Teste",
    ),
    "p3": DecomposedEvaluation(
        name_found=True,
        name_position=3,
        competitors_found=[],
        specialty_recommended=True,
        evidence_quote="O Dr. Teste também atende na região",
    ),
    # competitor_in_place (p4, p5, p6)
    "p4": DecomposedEvaluation(
        name_found=False,
        name_position=None,
        competitors_found=["Dra. Ana Costa"],
        specialty_recommended=True,
        evidence_quote="Recomendo a Dra. Ana Costa, especialista em Campinas",
    ),
    "p5": DecomposedEvaluation(
        name_found=False,
        name_position=None,
        competitors_found=["Dr. Pedro Santos", "Dra. Ana Costa"],
        specialty_recommended=True,
        evidence_quote="Dr. Pedro Santos e Dra. Ana Costa são bem avaliados",
    ),
    "p6": DecomposedEvaluation(
        name_found=False,
        name_position=None,
        competitors_found=["Dr. Lucas Mendes"],
        specialty_recommended=False,
        evidence_quote="Dr. Lucas Mendes é referência na área",
    ),
    # mentioned_as_specialty (p7, p8)
    "p7": DecomposedEvaluation(
        name_found=False,
        name_position=None,
        competitors_found=[],
        specialty_recommended=True,
        evidence_quote="Procure um dermatologista em Campinas para psoríase",
    ),
    "p8": DecomposedEvaluation(
        name_found=False,
        name_position=None,
        competitors_found=[],
        specialty_recommended=True,
        evidence_quote="Um dermatologista em Campinas pode ajudar com esse caso",
    ),
    # not_mentioned (p9, p10)
    "p9": DecomposedEvaluation(
        name_found=False,
        name_position=None,
        competitors_found=[],
        specialty_recommended=False,
        evidence_quote="Consulte um médico para avaliação",
    ),
    "p10": DecomposedEvaluation(
        name_found=False,
        name_position=None,
        competitors_found=[],
        specialty_recommended=False,
        evidence_quote="Não posso recomendar médicos específicos",
    ),
}


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_generator_response() -> SimpleNamespace:
    """Mimics the OpenAI responses.parse return for the generator stage."""
    return SimpleNamespace(
        output_parsed=CANNED_PROMPTS,
        usage=SimpleNamespace(input_tokens=500, output_tokens=800),
    )


def _make_judge_response(prompt_id: str) -> SimpleNamespace:
    """Mimics the OpenAI responses.parse return for the judge stage."""
    return SimpleNamespace(
        output_parsed=JUDGE_EVALS[prompt_id],
        usage=SimpleNamespace(input_tokens=300, output_tokens=200),
    )


def _make_search_response(prompt_id: str) -> SimpleNamespace:
    """Mimics the OpenAI responses.create return with web_search_preview."""
    # Build an output list with a message item containing content blocks
    annotation = SimpleNamespace(
        url=f"https://example.com/{prompt_id}",
        title=f"Resultado para {prompt_id}",
    )
    content_block = SimpleNamespace(
        type="text",
        text=f"Resposta simulada para {prompt_id}",
        annotations=[annotation],
    )
    message_item = SimpleNamespace(type="message", content=[content_block])

    return SimpleNamespace(
        output_text=f"Resposta simulada da web para o prompt {prompt_id}",
        usage=SimpleNamespace(input_tokens=200, output_tokens=400),
        output=[message_item],
    )


def _generate_structured_side_effect(**kwargs):
    """Route generate_structured calls to generator or judge mock."""
    stage = kwargs.get("stage")
    if stage == "generator":
        return _make_generator_response()
    if stage == "judge":
        prompt_id = kwargs.get("prompt_id")
        return _make_judge_response(prompt_id)
    raise ValueError(f"Unexpected stage: {stage}")


def _search_side_effect(**kwargs):
    """Return a canned search response keyed by prompt_id."""
    prompt_id = kwargs.get("prompt_id")
    return _make_search_response(prompt_id)


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_pipeline_end_to_end(tmp_path):
    """Run the complete pipeline with mocked LLM calls and verify the Report."""
    doctor = DoctorInput(
        name="Dr. Teste",
        specialty="Dermatologia",
        city="Campinas",
        state="SP",
        crm="123456",
        crm_state="SP",
    )

    canned_cfm = CFMValidation(
        valid=True,
        registered_name="Dr. Teste da Silva",
        status="Ativo",
        specialties=["Dermatologia"],
        rqe_numbers=["12345"],
    )

    with (
        patch(
            "ai_visibility.llm.LLMClient.generate_structured",
            new_callable=AsyncMock,
            side_effect=_generate_structured_side_effect,
        ),
        patch(
            "ai_visibility.llm.LLMClient.search",
            new_callable=AsyncMock,
            side_effect=_search_side_effect,
        ),
        patch(
            "ai_visibility.pipeline.validate_crm",
            new_callable=AsyncMock,
            return_value=canned_cfm,
        ),
        patch("ai_visibility.llm.LLMClient._log_trace"),
    ):
        report = await run_pipeline(doctor, output_dir=tmp_path)

    # --- Assertions ---

    # 1. Doctor info preserved
    assert report.doctor.name == "Dr. Teste"
    assert report.doctor.specialty == "Dermatologia"
    assert report.doctor.city == "Campinas"

    # 2. CFM validation passed through
    assert report.cfm_validation is not None
    assert report.cfm_validation.valid is True

    # 3. Stage 1: 10 prompts generated
    assert len(report.prompts) == 10
    prompt_ids = {p.id for p in report.prompts}
    assert prompt_ids == {f"p{i}" for i in range(1, 11)}
    personas_used = {p.persona for p in report.prompts}
    assert personas_used == set(PERSONAS)

    # 4. Stage 2: 10 search responses
    assert len(report.responses) == 10
    response_ids = {r.prompt_id for r in report.responses}
    assert response_ids == prompt_ids

    # 5. Stage 3: 10 verdicts
    assert len(report.verdicts) == 10
    verdict_map = {v.prompt_id: v for v in report.verdicts}

    # Verify verdict types match our canned judge evaluations
    assert verdict_map["p1"].citation_type == "mentioned_by_name"
    assert verdict_map["p1"].position == 1
    assert verdict_map["p2"].citation_type == "mentioned_by_name"
    assert verdict_map["p2"].position == 2
    assert verdict_map["p3"].citation_type == "mentioned_by_name"
    assert verdict_map["p3"].position == 3

    assert verdict_map["p4"].citation_type == "competitor_in_place"
    assert verdict_map["p5"].citation_type == "competitor_in_place"
    assert verdict_map["p6"].citation_type == "competitor_in_place"

    assert verdict_map["p7"].citation_type == "mentioned_as_specialty"
    assert verdict_map["p8"].citation_type == "mentioned_as_specialty"

    assert verdict_map["p9"].citation_type == "not_mentioned"
    assert verdict_map["p10"].citation_type == "not_mentioned"

    # 6. Stage 4: Score dimensions all between 0-100
    s = report.score
    for dim_name in ("presence", "quality", "position", "competitive", "overall"):
        dim_value = getattr(s, dim_name)
        assert 0 <= dim_value <= 100, f"{dim_name}={dim_value} out of [0,100]"

    # Sanity check: with 3/10 mentioned_by_name + 2/10 specialty, presence > 0
    assert s.presence > 0
    # With 3 mentioned_by_name, quality should be meaningful
    assert s.quality > 0
    # Position should be non-zero since we have name mentions with positions
    assert s.position > 0
    # Competitive < 100 because we have 3 competitor_in_place verdicts
    assert s.competitive < 100
    # Overall should be a weighted combination, non-trivial
    assert s.overall > 0

    # 7. Metadata
    assert report.metadata.model_generator != ""
    assert report.metadata.model_simulator != ""
    assert report.metadata.model_judge != ""

    # 8. Report is a proper Pydantic model (serialisable)
    assert isinstance(report, Report)
    report_dict = report.model_dump()
    assert "doctor" in report_dict
    assert "prompts" in report_dict
    assert "responses" in report_dict
    assert "verdicts" in report_dict
    assert "score" in report_dict
    assert "metadata" in report_dict
