"""Markdown reporter — generates a human-readable report.md."""

from pathlib import Path

from ai_visibility.models import Report
from ai_visibility.stages.scorer import generate_recommendations, get_benchmark


def render_markdown(report: Report, output_dir: Path) -> Path:
    doc = report.doctor
    s = report.score
    benchmark = get_benchmark(doc.specialty)

    location = doc.city
    if doc.neighborhood:
        location = f"{doc.city} ({doc.neighborhood})"
    if doc.state:
        location += f" - {doc.state}"

    lines: list[str] = []
    lines.append(f"# AI Visibility Report — {doc.name}\n")
    lines.append(f"**Especialidade:** {doc.specialty}  ")
    lines.append(f"**Cidade:** {location}  ")
    if doc.crm:
        lines.append(f"**CRM:** {doc.crm}/{doc.crm_state or '??'}  ")
    lines.append(
        f"**Gerado em:** {report.metadata.generated_at.strftime('%Y-%m-%d %H:%M')}\n"
    )

    # Score
    lines.append(f"## Score Geral: {s.overall:.0f} / 100\n")
    lines.append(f"Média da especialidade ({doc.specialty}): {benchmark:.0f}/100\n")

    lines.append("| Dimensão | Score | Peso | O que mede |")
    lines.append("|----------|-------|------|------------|")
    lines.append(f"| Visibilidade | {s.visibility:.1f} | 65% | Quão bem a IA conhece e cita o médico por nome |")
    lines.append(f"| Dominância | {s.dominance:.1f} | 35% | Participação de mercado frente aos concorrentes |")
    lines.append(f"| Presença Indireta | {s.indirect_presence:.1f} | — | % de prompts onde a IA recomendou a especialidade sem citar o médico (informativo) |")
    lines.append("")

    # One-line diagnosis
    mentioned_count = sum(
        1 for v in report.verdicts if v.citation_type == "mentioned_by_name"
    )
    competitor_count = sum(
        1 for v in report.verdicts if v.citation_type == "competitor_in_place"
    )
    total = len(report.verdicts)

    lines.append("## Diagnóstico em uma frase\n")
    if mentioned_count == 0:
        lines.append(
            f"O médico não aparece por nome nas recomendações de IA. "
            f"Em {competitor_count} de {total} prompts, outros profissionais foram citados."
        )
    elif mentioned_count < total / 2:
        lines.append(
            f"O médico aparece em {mentioned_count} de {total} prompts, "
            f"mas ainda perde espaço para concorrentes em {competitor_count} prompts."
        )
    else:
        lines.append(
            f"O médico tem boa visibilidade: aparece em {mentioned_count} de {total} prompts."
        )
    lines.append("")

    # Detail per prompt
    lines.append("## Detalhe por prompt\n")
    for v in report.verdicts:
        prompt = next((p for p in report.prompts if p.id == v.prompt_id), None)
        if prompt is None:
            continue

        status_icon = {
            "mentioned_by_name": "✅",
            "mentioned_as_specialty": "🔶",
            "competitor_in_place": "❌",
            "not_mentioned": "⬜",
        }.get(v.citation_type, "?")

        lines.append(f"### {v.prompt_id} — {prompt.persona}")
        lines.append(f'> "{prompt.text}"\n')
        lines.append(
            f"**Veredicto:** {status_icon} {v.citation_type} "
            f"(confiança {v.confidence:.2f})"
        )
        if v.position:
            lines.append(f"**Posição:** {v.position}º")
        lines.append(f'**Evidência:** "{v.evidence_quote}"')
        if v.competitors_named:
            lines.append(
                f"**Concorrentes citados:** {', '.join(v.competitors_named)}"
            )
        lines.append("")

    # Competitors ranking
    from collections import Counter

    all_competitors: list[str] = []
    for v in report.verdicts:
        all_competitors.extend(v.competitors_named)

    if all_competitors:
        counter = Counter(all_competitors)
        lines.append("## Top Concorrentes\n")
        lines.append("| Nome | Aparições | % |")
        lines.append("|------|-----------|---|")
        for comp_name, count in counter.most_common(10):
            pct = 100 * count / total
            lines.append(f"| {comp_name} | {count}/{total} | {pct:.0f}% |")
        lines.append("")

    # Recommendations
    recommendations = generate_recommendations(
        report.verdicts, report.score, doc.name, doc.specialty
    )
    lines.append("## Plano de ação\n")
    for i, rec in enumerate(recommendations, 1):
        lines.append(f"{i}. {rec}")
    lines.append("")

    # Metadata
    lines.append("---\n")
    lines.append(
        f"*Custo: ${report.metadata.total_cost_usd:.4f} · "
        f"Tokens: {report.metadata.total_tokens_in}→{report.metadata.total_tokens_out} · "
        f"Seed: {report.metadata.seed}*"
    )

    content = "\n".join(lines)
    path = output_dir / "report.md"
    path.write_text(content, encoding="utf-8")
    return path
