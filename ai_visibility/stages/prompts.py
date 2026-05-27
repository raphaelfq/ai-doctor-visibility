"""Stage 1 — Prompt Generator.

Generates 10 realistic patient prompts in PT-BR using an LLM,
each with a different persona (anxious layperson, specific clinical query,
insurance question, urgency, second opinion, etc.).

Design (SPEC §7.1, PRACTICES §4):
- Structured output via client.responses.parse
- Few-shot with positive and negative examples for diversity
- Cache by (specialty, city, neighborhood)
"""

import logging

from ai_visibility import cache as cache_mod
from ai_visibility.config import settings
from ai_visibility.llm import LLMClient
from ai_visibility.models import DoctorInput, GeneratedPrompts

logger = logging.getLogger(__name__)

GENERATOR_SYSTEM_PROMPT = """\
Você é um gerador de prompts de pacientes brasileiros realistas.

<tarefa>
Dado uma especialidade médica e uma cidade, gere exatamente 10 prompts que pacientes \
reais fariam a um assistente de IA (como ChatGPT) ao buscar esse tipo de médico.
</tarefa>

<regras>
- Cada prompt DEVE ter uma persona DIFERENTE da lista: leigo_ansioso, informado_específico, \
urgência, segunda_opinião, pediátrico, convênio_vs_particular, estético_eletivo, \
crônico_acompanhamento, preventivo, pediu_indicação
- Use todas as 10 personas, uma por prompt
- Prompts em português brasileiro coloquial e natural
- OBRIGATÓRIO: todo prompt DEVE mencionar a cidade ou bairro do paciente de forma natural \
(ex: "em Moema", "aqui em Campinas", "na região de Vila Mariana"). \
Sem localização, a busca não retorna resultados locais e o teste perde valor.
- NÃO mencione o nome de nenhum médico específico — o paciente está procurando, não conhece ninguém
- Varie: tom (formal/informal), comprimento (curto/longo), nível de detalhe clínico
- IDs devem ser "p1" até "p10"
</regras>

<exemplos_bons>
- "Tô com umas manchas estranhas na pele que apareceram do nada, preciso de um dermato urgente em Campinas"
- "Meu convênio é Unimed, preciso de ortopedista em Belo Horizonte que atenda, alguém sabe indicar?"
- "Já fui em 2 dermatologistas pra minha psoríase e nenhum resolveu. Quero alguém especializado de verdade em SP"
</exemplos_bons>

<exemplos_ruins_evitar>
- "Preciso de um dermatologista em São Paulo" (genérico demais, sem contexto)
- "Quem é o melhor dermatologista?" (todos iguais, sem variação de persona)
- "Qual médico você recomenda?" (não menciona cidade nem especialidade)
</exemplos_ruins_evitar>
"""


async def generate_prompts(
    doctor: DoctorInput,
    client: LLMClient,
) -> list:
    """Generate 10 diverse patient prompts for the given specialty and city."""
    # Check cache first
    key = cache_mod.cache_key(doctor.specialty, doctor.city, doctor.neighborhood)
    cached = cache_mod.get_cached(key)
    if cached is not None:
        return cached

    location = doctor.city
    if doctor.neighborhood:
        location = f"{doctor.neighborhood}, {doctor.city}"
    if doctor.state:
        location += f" - {doctor.state}"

    user_msg = (
        f"Especialidade: {doctor.specialty}\n"
        f"Local: {location}\n\n"
        "Gere 10 prompts diversos seguindo as regras."
    )

    try:
        response = await client.generate_structured(
            model=settings.model_generator,
            input=[
                {"role": "system", "content": GENERATOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            text_format=GeneratedPrompts,
            temperature=settings.temperature_generator,
            stage="generator",
        )
        result = response.output_parsed
        prompts = result.prompts if result else []
    except Exception as e:
        logger.error("Prompt generation failed for %s/%s: %s", doctor.specialty, doctor.city, e)
        raise

    # Cache for reuse across doctors of the same specialty × city
    if prompts:
        serialised = [p.model_dump() for p in prompts]
        cache_mod.set_cached(key, serialised)

    return prompts


if __name__ == "__main__":
    import asyncio
    from pathlib import Path

    from ai_visibility.llm import LLMClient

    async def _test():
        client = LLMClient(trace_path=Path("trace_test.jsonl"))
        doctor = DoctorInput(
            name="Dr. Teste",
            specialty="Dermatologia",
            city="Campinas",
            state="SP",
        )
        prompts = await generate_prompts(doctor, client)
        for p in prompts:
            print(f"[{p.id}] ({p.persona}) {p.text}")

    asyncio.run(_test())
