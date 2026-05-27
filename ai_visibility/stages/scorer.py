"""Stage 4 — Scorer.

Pure Python, deterministic score calculation. No LLM calls.
Same input → same output (±0 points).

2 independent dimensions measuring AI Citation visibility:
- visibility (65%): per-prompt score averaged — how well AI knows the doctor
- dominance (35%): market share — doctor's named mentions vs competitors
"""

from collections import Counter

from ai_visibility.models import ScoreBreakdown, Verdict

SPECIALTY_BENCHMARKS: dict[str, float] = {
    "Dermatologia": 25.0,
    "Cardiologia": 18.0,
    "Ortopedia": 20.0,
    "Ginecologia": 26.0,
    "Psiquiatria": 15.0,
    "Endocrinologia": 12.0,
    "Cirurgia Plástica": 28.0,
    "Obstetrícia": 22.0,
    "Neurologia": 17.0,
    "Oftalmologia": 20.0,
    "Urologia": 19.0,
    "Pediatria": 23.0,
    "Otorrinolaringologia": 14.0,
    "Gastroenterologia": 16.0,
    "Pneumologia": 13.0,
}

DEFAULT_BENCHMARK = 18.0


def _prompt_score(v: Verdict) -> float:
    """Score a single verdict on a 0–100 scale.

    - mentioned_by_name: 100 (pos 1) down to 10 (pos 10+), based on rank
    - mentioned_as_specialty: 15 (AI knows the specialty, not the doctor)
    - competitor_in_place / not_mentioned: 0
    """
    if v.citation_type == "mentioned_by_name":
        pos = v.position if v.position is not None else 5
        return max(10.0, (11 - pos) * 10.0)
    if v.citation_type == "mentioned_as_specialty":
        return 15.0
    return 0.0


def score(verdicts: list[Verdict]) -> ScoreBreakdown:
    """Calculate the AI Visibility Score from a list of verdicts.

    Dimensions:
    - visibility (65%): Average prompt score across all prompts. Measures
      how often and how prominently the AI names the doctor.
      Perfect = 10/10 named at position 1 → 100.

    - dominance (35%): Among prompts where ANY doctor was named
      (mentioned_by_name + competitor_in_place), what fraction named the
      target doctor? Measures competitive market share.
      0 if nobody was ever named (empty space, not a win).

    Overall = 0.65 × visibility + 0.35 × dominance → range [0, 100].
    """
    n = len(verdicts)
    if n == 0:
        return ScoreBreakdown(
            visibility=0.0, dominance=0.0, indirect_presence=0.0, overall=0.0,
        )

    # --- Visibility (65%) ---
    visibility = sum(_prompt_score(v) for v in verdicts) / n

    # --- Dominance (35%) ---
    by_name_count = sum(
        1 for v in verdicts if v.citation_type == "mentioned_by_name"
    )
    competitor_count = sum(
        1 for v in verdicts if v.citation_type == "competitor_in_place"
    )
    active = by_name_count + competitor_count
    dominance = (by_name_count / active * 100.0) if active > 0 else 0.0

    # --- Indirect Presence (informational, not in overall) ---
    specialty_count = sum(
        1 for v in verdicts if v.citation_type == "mentioned_as_specialty"
    )
    indirect_presence = (specialty_count / n) * 100.0

    # --- Overall (only visibility + dominance) ---
    overall = 0.65 * visibility + 0.35 * dominance

    return ScoreBreakdown(
        visibility=round(visibility, 1),
        dominance=round(dominance, 1),
        indirect_presence=round(indirect_presence, 1),
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

    by_name_count = sum(
        1 for v in verdicts if v.citation_type == "mentioned_by_name"
    )

    # Invisible — never named
    if by_name_count == 0:
        recs.append(
            "Nenhuma IA citou seu nome nos 10 prompts simulados. "
            "Você é invisível para pacientes que buscam via ChatGPT, Gemini ou Copilot."
        )

    # Competitors dominating
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

    # Low dominance despite being named sometimes
    if by_name_count > 0 and score_result.dominance < 40:
        recs.append(
            "Quando a IA cita nomes, concorrentes aparecem mais que você. "
            "Fortaleça sua presença digital com conteúdo educativo e perfil completo."
        )

    # Only generic mentions
    specialty_count = sum(
        1 for v in verdicts if v.citation_type == "mentioned_as_specialty"
    )
    if by_name_count == 0 and specialty_count > 0:
        recs.append(
            "A IA recomenda sua especialidade na sua cidade, mas não sabe seu nome. "
            "Crie conteúdo online vinculado ao seu nome + especialidade + cidade."
        )

    # Below benchmark
    if score_result.overall < benchmark:
        recs.append(
            f"Seu score ({score_result.overall:.0f}) está abaixo da média da "
            f"especialidade {specialty} ({benchmark:.0f}). "
            f"Construir uma presença digital estruturada pode mudar isso."
        )

    if not recs:
        recs.append(
            f"Sua visibilidade está acima da média ({score_result.overall:.0f} vs {benchmark:.0f}). "
            f"Continue publicando conteúdo e mantenha seu perfil atualizado."
        )

    return recs
