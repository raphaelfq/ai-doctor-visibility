"""Stage 4 — Scorer.

Pure Python, deterministic score calculation. No LLM calls.
Same input → same output (±0 points).

4 dimensions measuring AI Citation visibility (1 of 6 PRD dimensions):
- quality:  weighted average by citation type × confidence (40%)
- presence: % of prompts where doctor appeared (30%)
- position: rank when mentioned by name (20%)
- competitive: inverse of competitor displacement rate (10%)
"""

from collections import Counter

from ai_visibility.models import ScoreBreakdown, Verdict

QUALITY_VALUE: dict[str, int] = {
    "mentioned_by_name": 100,
    "mentioned_as_specialty": 30,
    "competitor_in_place": 10,
    "not_mentioned": 0,
}

SPECIALTY_BENCHMARKS: dict[str, float] = {
    "Dermatologia": 35.0,
    "Cardiologia": 28.0,
    "Ortopedia": 31.0,
    "Ginecologia": 38.0,
    "Psiquiatria": 25.0,
    "Endocrinologia": 22.0,
    "Cirurgia Plástica": 40.0,
    "Obstetrícia": 33.0,
    "Neurologia": 27.0,
    "Oftalmologia": 30.0,
    "Urologia": 29.0,
    "Pediatria": 35.0,
    "Otorrinolaringologia": 24.0,
    "Gastroenterologia": 26.0,
    "Pneumologia": 23.0,
}

DEFAULT_BENCHMARK = 30.0


def score(verdicts: list[Verdict]) -> ScoreBreakdown:
    """Calculate the AI Visibility Score from a list of verdicts."""
    n = len(verdicts)
    if n == 0:
        return ScoreBreakdown(
            presence=0.0, quality=0.0, position=0.0, competitive=0.0, overall=0.0
        )

    # Presence (30%): % of prompts where doctor appeared
    mentioned = [
        v for v in verdicts
        if v.citation_type in ("mentioned_by_name", "mentioned_as_specialty")
    ]
    presence = 100.0 * len(mentioned) / n

    # Quality (40%): weighted average of citation quality × confidence
    quality = (
        sum(QUALITY_VALUE[v.citation_type] * v.confidence for v in verdicts) / n
    )

    # Position (20%): higher rank = higher score (when mentioned by name)
    by_name = [
        v for v in verdicts
        if v.citation_type == "mentioned_by_name" and v.position is not None
    ]
    if by_name:
        position = (
            sum(max(0, (11 - v.position) * 10) for v in by_name) / len(by_name)
        )
    else:
        position = 0.0

    # Competitive (10%): inverse of competitor displacement rate
    competitor_count = sum(
        1 for v in verdicts if v.citation_type == "competitor_in_place"
    )
    competitive = 100.0 - (100.0 * competitor_count / n)

    # Overall: weighted combination
    overall = (
        0.40 * quality + 0.30 * presence + 0.20 * position + 0.10 * competitive
    )

    return ScoreBreakdown(
        presence=round(presence, 1),
        quality=round(quality, 1),
        position=round(position, 1),
        competitive=round(competitive, 1),
        overall=round(overall, 1),
    )


def get_benchmark(specialty: str) -> float:
    return SPECIALTY_BENCHMARKS.get(specialty, DEFAULT_BENCHMARK)


def generate_recommendations(
    verdicts: list[Verdict],
    score_result: ScoreBreakdown,
    doctor_name: str,
    specialty: str,
) -> list[str]:
    """Generate actionable recommendations based on the score breakdown."""
    recs: list[str] = []
    benchmark = get_benchmark(specialty)

    if score_result.presence < 20:
        recs.append(
            f"Você é praticamente invisível para IAs de busca. "
            f"Em {int(10 - score_result.presence / 10)} de 10 prompts simulados, "
            f"seu nome não apareceu."
        )

    # Competitor dominance
    all_competitors: list[str] = []
    for v in verdicts:
        all_competitors.extend(v.competitors_named)
    if all_competitors:
        top = Counter(all_competitors).most_common(3)
        if top:
            top_name, top_count = top[0]
            recs.append(
                f"{top_name} aparece em {top_count} de {len(verdicts)} prompts. "
                f"Esse profissional está capturando pacientes que poderiam ser seus."
            )

    if score_result.position < 50 and score_result.presence > 0:
        recs.append(
            "Quando citado, você aparece em posições baixas. "
            "IAs tendem a priorizar médicos com perfil online completo e conteúdo educativo."
        )

    if score_result.overall < benchmark:
        recs.append(
            f"Seu score ({score_result.overall:.0f}) está abaixo da média da "
            f"especialidade {specialty} ({benchmark:.0f}). "
            f"Construir uma presença digital estruturada pode mudar isso."
        )

    if score_result.quality < 30:
        recs.append(
            "Construa uma entidade verificada (CRM/RQE) com schema correto — "
            "você praticamente não existe na camada de IA."
        )

    if not recs:
        recs.append(
            f"Sua visibilidade está acima da média ({score_result.overall:.0f} vs {benchmark:.0f}). "
            f"Continue publicando conteúdo e mantenha seu perfil atualizado."
        )

    return recs
