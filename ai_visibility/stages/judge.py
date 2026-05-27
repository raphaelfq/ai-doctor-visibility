"""Stage 3 — LLM-as-Judge.

Classifies how the target doctor appears (or doesn't) in each simulated response.

Design:
- Decomposed evaluation: 3 binary questions instead of 1 multi-class decision
- Chain-of-thought reasoning before each answer (G-Eval pattern)
- Verdict derived deterministically from binary answers
- Structured output via client.responses.parse
- temperature=0 for reproducibility
- XML tags to separate instruction/data/rules
- Pluggable via BaseJudge ABC

References:
- G-Eval: https://www.confident-ai.com/blog/why-llm-as-a-judge-is-the-best-llm-evaluation-method
- Decomposition: https://montecarlo.ai/blog-llm-as-judge/ ("LLMs are more effective with single objective tasks")
- Industry standard: https://www.airops.com/blog/llm-brand-citation-tracking
"""

import asyncio
import logging
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from ai_visibility.config import settings
from ai_visibility.llm import LLMClient
from ai_visibility.models import (
    DoctorInput,
    GeneratedPrompt,
    SimulatedResponse,
    Verdict,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Decomposed evaluation model — 3 binary questions with chain-of-thought
# ---------------------------------------------------------------------------


class DecomposedEvaluation(BaseModel):
    """Structured output for the decomposed judge.

    3 binary questions → verdict derived deterministically.
    No reasoning fields — keeps output small and fast (~2s vs ~160s).
    """

    # Q1: Is the target doctor's name in the response?
    name_found: bool = Field(
        description="O nome próprio do médico-alvo aparece literalmente na resposta?"
    )
    name_position: int | None = Field(
        None,
        ge=1,
        description="Se name_found=true, posição na lista (1=primeiro). Se false, null.",
    )

    # Q2: Other doctors/clinics named?
    competitors_found: list[str] = Field(
        description="Nomes próprios de outros médicos/clínicas citados. Vazio se nenhum."
    )

    # Q3: Concrete specialty recommendation?
    specialty_recommended: bool = Field(
        description="A IA recomendou concretamente buscar a especialidade "
        "(com cidade ou condição)? Conselho genérico = false."
    )

    # Evidence
    evidence_quote: str = Field(
        description="Trecho LITERAL mais relevante da resposta (max 150 chars)."
    )


JUDGE_SYSTEM_PROMPT = """\
Analise se um médico-alvo aparece em uma resposta de IA. Responda 3 perguntas:

1. O NOME do médico-alvo aparece na resposta? (nome completo ou parcial inequívoco)
   - Ignore títulos (Dr., Dra., Prof.) ao comparar — "Maísa Mattieli" = "Dra Maísa Mattieli"
   - Sobrenome + primeiro nome basta — "Fernando Lopes" = "Dr. Fernando Lopes da Silva"
   - Ignore diferenças de acento — "Maisa" = "Maísa"
   - Se sim, em que posição na lista? (1=primeiro)

2. Outros médicos/clínicas são citados PELO NOME? Liste todos.

3. A resposta faz RECOMENDAÇÃO CONCRETA da especialidade (com cidade ou condição)?
   - "Procure dermatologista em Campinas para psoríase" = SIM
   - "Vá ao dermatologista" / "Posso ajudar a encontrar" = NÃO (genérico)

evidence_quote: trecho LITERAL da resposta, max 150 caracteres.
"""


def _derive_verdict(
    eval_result: DecomposedEvaluation,
    prompt_id: str,
) -> Verdict:
    """Derive citation_type deterministically from binary answers.

    Decision tree:
    1. name_found=True → mentioned_by_name
    2. name_found=False AND competitors_found → competitor_in_place
    3. name_found=False AND no competitors AND specialty_recommended → mentioned_as_specialty
    4. else → not_mentioned

    Confidence derived from reasoning clarity:
    - name_found=True: 1.0 (binary, unambiguous)
    - competitors with names: 0.95
    - specialty_recommended: 0.7 (inherently more subjective)
    - not_mentioned: 0.9
    """
    if eval_result.name_found:
        return Verdict(
            prompt_id=prompt_id,
            citation_type="mentioned_by_name",
            confidence=1.0,
            position=eval_result.name_position,
            evidence_quote=eval_result.evidence_quote,
            competitors_named=eval_result.competitors_found,
        )

    if eval_result.competitors_found:
        return Verdict(
            prompt_id=prompt_id,
            citation_type="competitor_in_place",
            confidence=0.95,
            evidence_quote=eval_result.evidence_quote,
            competitors_named=eval_result.competitors_found,
        )

    if eval_result.specialty_recommended:
        return Verdict(
            prompt_id=prompt_id,
            citation_type="mentioned_as_specialty",
            confidence=0.7,
            evidence_quote=eval_result.evidence_quote,
            competitors_named=[],
        )

    return Verdict(
        prompt_id=prompt_id,
        citation_type="not_mentioned",
        confidence=0.9,
        evidence_quote=eval_result.evidence_quote,
        competitors_named=[],
    )


# ---------------------------------------------------------------------------
# Judge interface + implementations
# ---------------------------------------------------------------------------


class BaseJudge(ABC):
    """Protocol for judge implementations (pluggable — SPEC §2)."""

    @abstractmethod
    async def evaluate(
        self,
        doctor: DoctorInput,
        prompt: GeneratedPrompt,
        response: SimulatedResponse,
    ) -> Verdict: ...


_JUDGE_MAX_RETRIES = 2


class OpenAIJudge(BaseJudge):
    """Judge V3: decomposed binary questions with chain-of-thought."""

    def __init__(self, client: LLMClient):
        self._client = client

    async def evaluate(
        self,
        doctor: DoctorInput,
        prompt: GeneratedPrompt,
        response: SimulatedResponse,
    ) -> Verdict:
        user_msg = f"""\
<medico_alvo>
Nome: {doctor.name}
Especialidade: {doctor.specialty}
Cidade: {doctor.city}
</medico_alvo>

<prompt_paciente>
{prompt.text}
</prompt_paciente>

<resposta_simulada>
{response.raw_text}
</resposta_simulada>

Analise a resposta e responda as 3 perguntas com raciocínio."""

        last_error: Exception | None = None
        for attempt in range(_JUDGE_MAX_RETRIES + 1):
            try:
                api_response = await self._client.generate_structured(
                    model=settings.model_judge,
                    input=[
                        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    text_format=DecomposedEvaluation,
                    temperature=settings.temperature_judge,
                    stage="judge",
                    prompt_id=prompt.id,
                )

                eval_result = api_response.output_parsed
                if eval_result is None:
                    raise ValueError("output_parsed is None (truncated JSON)")

                return _derive_verdict(eval_result, prompt.id)
            except Exception as e:
                last_error = e
                if attempt < _JUDGE_MAX_RETRIES:
                    wait = 2 ** attempt
                    logger.warning(
                        "Judge retry %d/%d for prompt %s (%s), waiting %ds",
                        attempt + 1, _JUDGE_MAX_RETRIES, prompt.id, e, wait,
                    )
                    await asyncio.sleep(wait)

        logger.error("Judge failed after %d retries for prompt %s: %s",
                      _JUDGE_MAX_RETRIES + 1, prompt.id, last_error)
        return Verdict(
            prompt_id=prompt.id,
            citation_type="not_mentioned",
            confidence=0.0,
            evidence_quote=f"[ERRO: {type(last_error).__name__}: {last_error}]",
        )


async def judge_all(
    doctor: DoctorInput,
    prompts: list[GeneratedPrompt],
    responses: list[SimulatedResponse],
    client: LLMClient,
) -> list[Verdict]:
    """Run the judge on all prompt-response pairs in parallel."""
    judge = OpenAIJudge(client)

    response_map = {r.prompt_id: r for r in responses}

    tasks = []
    for prompt in prompts:
        resp = response_map.get(prompt.id)
        if resp is None:
            continue
        tasks.append(judge.evaluate(doctor, prompt, resp))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    verdicts: list[Verdict] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning("Judge evaluation failed for prompt %s: %s", prompts[i].id, result)
            verdicts.append(
                Verdict(
                    prompt_id=prompts[i].id,
                    citation_type="not_mentioned",
                    confidence=0.0,
                    evidence_quote=f"[ERRO: {type(result).__name__}: {result}]",
                )
            )
        else:
            verdicts.append(result)

    return verdicts


if __name__ == "__main__":
    import asyncio
    from pathlib import Path

    async def _test():
        client = LLMClient(trace_path=Path("trace_test.jsonl"))
        doctor = DoctorInput(
            name="Dr. Fernando Lopes",
            specialty="Dermatologia",
            city="Campinas",
        )
        prompt = GeneratedPrompt(
            id="p1",
            text="Preciso de dermato bom em Campinas",
            persona="leigo_ansioso",
            intent_summary="Busca dermato genérico",
        )
        response = SimulatedResponse(
            prompt_id="p1",
            raw_text="Recomendo o Dr. Fernando Lopes, dermatologista muito bem avaliado em Campinas. Também a Dra. Patricia Moreno.",
            model="test",
            tokens_in=0,
            tokens_out=0,
            latency_ms=0,
        )
        verdicts = await judge_all(doctor, [prompt], [response], client)
        for v in verdicts:
            print(v.model_dump_json(indent=2))

    asyncio.run(_test())
