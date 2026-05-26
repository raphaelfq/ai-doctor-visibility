"""Stage 4 — Scorer.

Pure Python, deterministic score calculation. No LLM calls.
Same input → same output (±0 points).

7 dimensions covering 4 of 6 PRD dimensions:
- presence + quality + position + competitive → Citação em IA (PRD)
- citation_strength → Encontrabilidade + Entidade (PRD)
- share_of_voice → Citação em IA competitiva (PRD)
- sentiment → Reputação (PRD, proxy via heurística)

Overall = weighted combination of all 7.
"""

import re
from urllib.parse import urlparse

from ai_visibility.models import ScoreBreakdown, SimulatedResponse, Verdict

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

# Keywords for sentiment heuristic
_POSITIVE_DETAIL = [
    "especialista", "especialização", "especializado", "referência",
    "experiência", "reconhecido", "titulado",
]
_POSITIVE_TONE = [
    "humanizado", "excelente", "recomendado", "renomado",
    "muito bem avaliado", "destaque", "premiado",
]


# ---------------------------------------------------------------------------
# Core dimensions (from V3)
# ---------------------------------------------------------------------------


def _presence(verdicts: list[Verdict]) -> float:
    n = len(verdicts)
    if n == 0:
        return 0.0
    mentioned = [
        v for v in verdicts
        if v.citation_type in ("mentioned_by_name", "mentioned_as_specialty")
    ]
    return 100.0 * len(mentioned) / n


def _quality(verdicts: list[Verdict]) -> float:
    n = len(verdicts)
    if n == 0:
        return 0.0
    return sum(QUALITY_VALUE[v.citation_type] * v.confidence for v in verdicts) / n


def _position(verdicts: list[Verdict]) -> float:
    by_name = [
        v for v in verdicts
        if v.citation_type == "mentioned_by_name" and v.position is not None
    ]
    if not by_name:
        return 0.0
    return sum(max(0, (11 - v.position) * 10) for v in by_name) / len(by_name)


def _competitive(verdicts: list[Verdict]) -> float:
    n = len(verdicts)
    if n == 0:
        return 0.0
    competitor_count = sum(1 for v in verdicts if v.citation_type == "competitor_in_place")
    return 100.0 - (100.0 * competitor_count / n)


# ---------------------------------------------------------------------------
# New dimensions (V4)
# ---------------------------------------------------------------------------


def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _doctor_name_matches_citation(doctor_name: str, url: str, title: str) -> bool:
    """Check if a citation URL or title relates to the target doctor."""
    # Normalize doctor name: "Dr. Fernando Lopes" → ["fernando", "lopes"]
    name_parts = [
        p.lower() for p in doctor_name.split()
        if p.lower() not in ("dr.", "dra.", "dr", "dra", "de", "da", "do", "dos", "das")
    ]
    if len(name_parts) < 1:
        return False

    # Check URL (e.g., fernandolopesdermato.com)
    url_lower = url.lower()
    domain = _extract_domain(url)
    last_name = name_parts[-1] if name_parts else ""

    # Name parts joined in domain (fernandolopes, karinazold)
    joined = "".join(name_parts)
    if joined in domain:
        return True

    # Check title
    title_lower = title.lower()
    if last_name and len(last_name) > 3 and last_name in title_lower:
        # Verify it's not a different person with same last name
        if any(part in title_lower for part in name_parts[:1]):
            return True

    return False


def citation_strength(
    responses: list[SimulatedResponse],
    doctor_name: str,
) -> float:
    """Score 0-100 based on quality of sources citing the doctor.

    Components:
    - Own site cited (40pts): indicates strong entity/SEO
    - Google Maps/GBP (25pts): indicates local presence
    - Doctoralia/platforms (15pts): indicates indexed reputation
    - Source diversity ≥3 (20pts): indicates broad digital footprint
    """
    own_site_cited = 0
    google_maps_cited = 0
    platform_cited = 0  # Doctoralia, BoaConsulta, etc.
    unique_doctor_sources: set[str] = set()

    for resp in responses:
        for cit in resp.citations:
            if _doctor_name_matches_citation(doctor_name, cit.url, cit.title):
                own_site_cited += 1
                unique_doctor_sources.add(_extract_domain(cit.url))

            if "google.com/maps" in cit.url:
                if _doctor_name_matches_citation(doctor_name, cit.url, cit.title):
                    google_maps_cited += 1

            domain = _extract_domain(cit.url)
            if domain in ("doctoralia.com.br", "boaconsulta.com", "yelp.com"):
                if _doctor_name_matches_citation(doctor_name, cit.url, cit.title):
                    platform_cited += 1

    points = 0.0
    if own_site_cited > 0:
        points += 40.0
    if google_maps_cited > 0:
        points += 25.0
    if platform_cited > 0:
        points += 15.0
    n_sources = len(unique_doctor_sources)
    if n_sources >= 3:
        points += 20.0
    elif n_sources >= 1:
        points += 10.0

    return min(points, 100.0)


def share_of_voice(verdicts: list[Verdict]) -> float:
    """(doctor mentions / all doctor mentions) × 100.

    Industry standard metric for brand visibility in AI search.
    """
    doctor_mentions = sum(
        1 for v in verdicts if v.citation_type == "mentioned_by_name"
    )
    total_competitor_mentions = sum(len(v.competitors_named) for v in verdicts)
    total_mentions = doctor_mentions + total_competitor_mentions

    if total_mentions == 0:
        return 0.0

    return 100.0 * doctor_mentions / total_mentions


def sentiment_score(
    responses: list[SimulatedResponse],
    verdicts: list[Verdict],
) -> float:
    """Score 0-100 based on richness and tone of mentions.

    Heuristic-based (no LLM), deterministic. Looks for:
    - Rating with reviews (e.g. "5.0 (30 avaliações)") → 30pts
    - Address/CEP → 20pts
    - Specialization keywords → 25pts
    - Positive tone keywords → 25pts
    """
    # Match responses to verdicts by prompt_id
    response_map = {r.prompt_id: r for r in responses}
    mentioned = [
        response_map[v.prompt_id]
        for v in verdicts
        if v.citation_type == "mentioned_by_name" and v.prompt_id in response_map
    ]

    if not mentioned:
        return 0.0

    total = 0.0
    for resp in mentioned:
        text = resp.raw_text.lower()
        points = 0.0

        # Rating pattern: "5.0 (30 avaliações)"
        if re.search(r"\d\.\d\s*\(\d+\s*avaliações?\)", text):
            points += 30.0

        # Address: CEP pattern (xxxxx-xxx)
        if re.search(r"\d{5}-\d{3}", text):
            points += 20.0

        # Specialization keywords
        if any(kw in text for kw in _POSITIVE_DETAIL):
            points += 25.0

        # Positive tone keywords
        if any(kw in text for kw in _POSITIVE_TONE):
            points += 25.0

        total += min(points, 100.0)

    return total / len(mentioned)


# ---------------------------------------------------------------------------
# Overall score (V4: 7 dimensions)
# ---------------------------------------------------------------------------


def score(
    verdicts: list[Verdict],
    responses: list[SimulatedResponse] | None = None,
    doctor_name: str = "",
) -> ScoreBreakdown:
    """Calculate the AI Visibility Score from verdicts and responses."""
    n = len(verdicts)
    if n == 0:
        return ScoreBreakdown(
            presence=0.0, quality=0.0, position=0.0, competitive=0.0,
            citation_strength=0.0, share_of_voice=0.0, sentiment=0.0,
            overall=0.0,
        )

    # Core dimensions (V3)
    pres = _presence(verdicts)
    qual = _quality(verdicts)
    pos = _position(verdicts)
    comp = _competitive(verdicts)

    # New dimensions (V4) — require responses
    cit_str = citation_strength(responses, doctor_name) if responses else 0.0
    sov = share_of_voice(verdicts)
    sent = sentiment_score(responses, verdicts) if responses else 0.0

    # Weighted overall (7 dimensions)
    overall = (
        0.25 * qual
        + 0.20 * pres
        + 0.15 * cit_str
        + 0.15 * sov
        + 0.10 * pos
        + 0.10 * sent
        + 0.05 * comp
    )

    return ScoreBreakdown(
        presence=round(pres, 1),
        quality=round(qual, 1),
        position=round(pos, 1),
        competitive=round(comp, 1),
        citation_strength=round(cit_str, 1),
        share_of_voice=round(sov, 1),
        sentiment=round(sent, 1),
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
            f"seu nome não apareceu em nenhuma forma."
        )

    # Competitor dominance
    all_competitors: list[str] = []
    for v in verdicts:
        all_competitors.extend(v.competitors_named)
    if all_competitors:
        from collections import Counter
        top = Counter(all_competitors).most_common(3)
        if top:
            top_name, top_count = top[0]
            recs.append(
                f"{top_name} aparece em {top_count} de {len(verdicts)} prompts. "
                f"Esse profissional está capturando pacientes que poderiam ser seus."
            )

    # Citation strength
    if score_result.citation_strength < 30:
        recs.append(
            "Sua presença digital é fraca: seu site não aparece como fonte citada pelas IAs. "
            "Ter um site próprio com schema correto e Google Business Profile atualizado "
            "aumenta significativamente a chance de ser citado."
        )

    # Share of voice
    if score_result.share_of_voice < 20:
        recs.append(
            f"Seu share of voice é muito baixo ({score_result.share_of_voice:.0f}%). "
            f"Concorrentes dominam as menções na sua região."
        )

    # Sentiment
    if score_result.sentiment < 30 and score_result.presence > 0:
        recs.append(
            "Quando citado, as menções são superficiais (sem avaliações, sem detalhes). "
            "Médicos com reviews positivos e perfis completos recebem menções mais ricas."
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
