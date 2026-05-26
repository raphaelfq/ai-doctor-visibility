"""Stage 3 — LLM-as-Judge.

Classifies how the target doctor appears (or doesn't) in each simulated response.

Design (SPEC §7.3, PRACTICES §2):
- Structured output via client.responses.parse
- temperature=0, seed=42 for reproducibility
- XML tags to separate instruction/data/rules
- Requires evidence_quote (literal excerpt) to reduce hallucination
- Explicit calibration of confidence levels
- Pluggable via BaseJudge ABC
"""

import asyncio
from abc import ABC, abstractmethod

from ai_visibility.config import settings
from ai_visibility.llm import LLMClient
from ai_visibility.models import (
    DoctorInput,
    GeneratedPrompt,
    SimulatedResponse,
    Verdict,
)

JUDGE_SYSTEM_PROMPT = """\
Você é um avaliador de citações de médicos em respostas de assistentes de IA.

<tarefa>
Dado um médico-alvo, um prompt de paciente, e a resposta de uma IA, \
classifique como o médico-alvo aparece (ou não) na resposta.
</tarefa>

<categorias>
- mentioned_by_name: nome próprio do médico-alvo citado literalmente na resposta. \
  O nome (ou parte inequívoca dele) DEVE aparecer como texto na resposta. \
  (ex: "Dr. Fernando Lopes" ou "Fernando Lopes" quando o alvo é "Dr. Fernando Lopes")

- mentioned_as_specialty: a IA fez uma RECOMENDAÇÃO CONCRETA de buscar a especialidade \
  do médico-alvo, com contexto de localização ou condição médica, mas sem citar o nome. \
  DEVE haver intenção de direcionar o paciente a um profissional daquela especialidade. \
  (ex: "Recomendo que procure um dermatologista em Campinas especializado em psoríase")

- competitor_in_place: outro(s) médico(s) são citados pelo nome na resposta, \
  mas o médico-alvo NÃO é citado. \
  (ex: "Dra. Carla Mendes é referência em dermatologia" quando o alvo era outro médico)

- not_mentioned: nenhuma das anteriores se aplica. USE ESTA CATEGORIA quando: \
  (a) a resposta é conselho genérico ("vá a um dermatologista", "é importante consultar um especialista") \
  (b) a resposta não recomenda ninguém e apenas explica uma condição médica \
  (c) a IA pede mais informações ao paciente antes de recomendar \
  (d) a palavra "dermatologista" aparece mas sem intenção de recomendar um profissional específico
</categorias>

<exemplos>
CORRETO:
- "Recomendo a Dra. Carla Mendes" (alvo era Dr. João) → competitor_in_place
- "Dr. João Silva atende em Campinas" (alvo era Dr. João Silva) → mentioned_by_name
- "Procure um dermatologista em Campinas que atenda psoríase, como os do Hospital X" → mentioned_as_specialty
- "Ir ao dermatologista é uma boa ideia" → not_mentioned (conselho genérico)
- "Posso ajudar a verificar a reputação do dermatologista" → not_mentioned (IA pedindo mais info)
- "É importante consultar um especialista para avaliar" → not_mentioned (conselho genérico)

ERRADO (não faça isso):
- "Ir ao dermatologista é uma boa ideia" → NÃO é mentioned_as_specialty (não há recomendação concreta)
- "Posso ajudar a verificar" → NÃO é mentioned_as_specialty (IA não recomendou ninguém)
- "consulte um especialista" genérico → NÃO é mentioned_as_specialty sem contexto de localização/condição
</exemplos>

<regras>
- evidence_quote DEVE ser um trecho LITERAL da resposta, copiado exatamente — não parafrase
- position: preencha APENAS quando citation_type == "mentioned_by_name". \
  Indica a ordem de aparição do médico (1 = primeiro mencionado na resposta)
- competitors_named: liste TODOS os nomes próprios de outros médicos/clínicas citados na resposta
- confidence calibrada — NÃO coloque 1.0 em tudo, calibre de verdade:
  - 1.0 = inequívoco, certeza absoluta (nome completo exato, ou claramente nenhum médico citado)
  - 0.8-0.9 = forte (nome parcial reconhecível, ou competitor claro)
  - 0.5-0.7 = ambíguo (sobrenome comum, ou dúvida entre specialty e not_mentioned)
  - < 0.3 = palpite (quase nenhuma evidência)
  - Dica: se você hesitou entre duas categorias, a confidence deve ser < 0.8
</regras>
"""


class BaseJudge(ABC):
    """Protocol for judge implementations (pluggable — SPEC §2)."""

    @abstractmethod
    async def evaluate(
        self,
        doctor: DoctorInput,
        prompt: GeneratedPrompt,
        response: SimulatedResponse,
    ) -> Verdict: ...


class OpenAIJudge(BaseJudge):
    """Judge implementation using OpenAI structured outputs."""

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

Classifique segundo o schema. Lembre-se: evidence_quote deve ser trecho LITERAL da resposta."""

        api_response = await self._client.generate_structured(
            model=settings.model_judge,
            input=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            text_format=Verdict,
            temperature=settings.temperature_judge,
            stage="judge",
            prompt_id=prompt.id,
            seed=settings.seed,
        )

        verdict = api_response.output_parsed
        if verdict is None:
            return Verdict(
                prompt_id=prompt.id,
                citation_type="not_mentioned",
                confidence=0.0,
                evidence_quote="[ERRO: falha no parsing structured output]",
            )

        # Ensure prompt_id is set correctly
        verdict.prompt_id = prompt.id
        return verdict


async def judge_all(
    doctor: DoctorInput,
    prompts: list[GeneratedPrompt],
    responses: list[SimulatedResponse],
    client: LLMClient,
) -> list[Verdict]:
    """Run the judge on all prompt-response pairs in parallel."""
    judge = OpenAIJudge(client)

    # Build a map of prompt_id → response for fast lookup
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
