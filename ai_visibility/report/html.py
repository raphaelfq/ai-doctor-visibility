"""HTML reporter — generates a static report.html with Tailwind CSS and SVG gauge."""

from collections import Counter
from pathlib import Path

from ai_visibility.models import Report
from ai_visibility.stages.scorer import generate_recommendations, get_benchmark


def _score_color(score: float) -> str:
    if score <= 30:
        return "#ef4444"  # red
    if score <= 60:
        return "#f59e0b"  # amber
    return "#22c55e"  # green


def _score_label(score: float) -> str:
    if score <= 20:
        return "Invisível"
    if score <= 40:
        return "Baixa"
    if score <= 60:
        return "Moderada"
    if score <= 80:
        return "Boa"
    return "Excelente"


def render_html(report: Report, output_dir: Path) -> Path:
    doc = report.doctor
    s = report.score
    benchmark = get_benchmark(doc.specialty)
    color = _score_color(s.overall)
    label = _score_label(s.overall)

    location = doc.city
    if doc.neighborhood:
        location = f"{doc.city} ({doc.neighborhood})"
    if doc.state:
        location += f" - {doc.state}"

    # Build verdict rows
    verdict_rows = ""
    for v in report.verdicts:
        prompt = next((p for p in report.prompts if p.id == v.prompt_id), None)
        if not prompt:
            continue

        bg = {
            "mentioned_by_name": "bg-green-50",
            "mentioned_as_specialty": "bg-yellow-50",
            "competitor_in_place": "bg-red-50",
            "not_mentioned": "bg-gray-50",
        }.get(v.citation_type, "bg-gray-50")

        icon = {
            "mentioned_by_name": "✅",
            "mentioned_as_specialty": "🔶",
            "competitor_in_place": "❌",
            "not_mentioned": "⬜",
        }.get(v.citation_type, "?")

        competitors_str = ", ".join(v.competitors_named) if v.competitors_named else "—"
        pos_str = f"#{v.position}" if v.position else "—"

        verdict_rows += f"""
        <tr class="{bg}">
            <td class="px-4 py-3 text-sm font-medium">{v.prompt_id}</td>
            <td class="px-4 py-3 text-sm max-w-md">{prompt.text[:120]}{'...' if len(prompt.text) > 120 else ''}</td>
            <td class="px-4 py-3 text-sm text-center">{icon}</td>
            <td class="px-4 py-3 text-sm">{v.citation_type.replace('_', ' ')}</td>
            <td class="px-4 py-3 text-sm text-center">{v.confidence:.0%}</td>
            <td class="px-4 py-3 text-sm text-center">{pos_str}</td>
            <td class="px-4 py-3 text-sm">{competitors_str}</td>
        </tr>"""

    # Build competitor cards
    all_competitors: list[str] = []
    for v in report.verdicts:
        all_competitors.extend(v.competitors_named)
    counter = Counter(all_competitors)
    total = len(report.verdicts)

    competitor_cards = ""
    for comp_name, count in counter.most_common(6):
        pct = 100 * count / total
        competitor_cards += f"""
        <div class="bg-white rounded-xl shadow-sm border p-4">
            <div class="font-semibold text-gray-900">{comp_name}</div>
            <div class="text-sm text-gray-500 mt-1">Aparece em {count}/{total} prompts</div>
            <div class="mt-2 bg-gray-200 rounded-full h-2">
                <div class="bg-blue-600 rounded-full h-2" style="width: {pct}%"></div>
            </div>
        </div>"""

    # Recommendations
    recommendations = generate_recommendations(
        report.verdicts, report.score, doc.name, doc.specialty
    )
    rec_items = ""
    for i, rec in enumerate(recommendations, 1):
        rec_items += f'<li class="py-2">{rec}</li>'

    # CFM badge
    cfm_badge = ""
    if report.cfm_validation:
        cfm = report.cfm_validation
        if cfm.valid is True:
            cfm_badge = f'<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">✓ CRM Verificado</span>'
        elif cfm.valid is False:
            cfm_badge = f'<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">✗ CRM Inválido</span>'
        else:
            cfm_badge = f'<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">⚠ Verificação Pendente</span>'

    # SVG gauge offset: circumference = 2 * π * 45 ≈ 283
    offset = 283 * (1 - s.overall / 100)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Visibility Report — {doc.name}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>body {{ font-family: 'Inter', sans-serif; }}</style>
</head>
<body class="bg-gray-50 min-h-screen">
    <div class="max-w-5xl mx-auto px-4 py-8">

        <!-- Header -->
        <div class="bg-white rounded-2xl shadow-sm border p-8 mb-6">
            <div class="flex items-start justify-between">
                <div>
                    <h1 class="text-2xl font-bold text-gray-900">{doc.name}</h1>
                    <p class="text-gray-600 mt-1">{doc.specialty} — {location}</p>
                    {f'<p class="text-gray-500 text-sm mt-1">CRM: {doc.crm}/{doc.crm_state}</p>' if doc.crm else ''}
                    <div class="mt-2">{cfm_badge}</div>
                </div>
                <div class="text-right text-sm text-gray-400">
                    {report.metadata.generated_at.strftime('%d/%m/%Y %H:%M')}
                </div>
            </div>
        </div>

        <!-- Score Gauge -->
        <div class="bg-white rounded-2xl shadow-sm border p-8 mb-6 text-center">
            <h2 class="text-lg font-semibold text-gray-700 mb-4">AI Visibility Score</h2>
            <div class="flex justify-center">
                <svg class="w-48 h-48" viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="45" fill="none" stroke="#e5e7eb" stroke-width="8"/>
                    <circle cx="50" cy="50" r="45" fill="none"
                        stroke="{color}" stroke-width="8" stroke-linecap="round"
                        stroke-dasharray="283" stroke-dashoffset="{offset:.1f}"
                        transform="rotate(-90 50 50)"
                        style="transition: stroke-dashoffset 1s ease-in-out"/>
                    <text x="50" y="46" text-anchor="middle" font-size="22" font-weight="700" fill="#111827">{s.overall:.0f}</text>
                    <text x="50" y="58" text-anchor="middle" font-size="8" fill="#6b7280">/100</text>
                    <text x="50" y="70" text-anchor="middle" font-size="7" fill="{color}">{label}</text>
                </svg>
            </div>
            <p class="text-sm text-gray-500 mt-2">
                Média da especialidade ({doc.specialty}): <strong>{benchmark:.0f}/100</strong>
            </p>

            <!-- Dimension bars -->
            <div class="grid grid-cols-2 gap-4 mt-6 max-w-lg mx-auto text-left">
                <div>
                    <div class="flex justify-between text-sm text-gray-600"><span>Presença</span><span>{s.presence:.0f}</span></div>
                    <div class="bg-gray-200 rounded-full h-2 mt-1"><div class="bg-blue-500 rounded-full h-2" style="width: {s.presence}%"></div></div>
                </div>
                <div>
                    <div class="flex justify-between text-sm text-gray-600"><span>Qualidade</span><span>{s.quality:.0f}</span></div>
                    <div class="bg-gray-200 rounded-full h-2 mt-1"><div class="bg-blue-500 rounded-full h-2" style="width: {s.quality}%"></div></div>
                </div>
                <div>
                    <div class="flex justify-between text-sm text-gray-600"><span>Posição</span><span>{s.position:.0f}</span></div>
                    <div class="bg-gray-200 rounded-full h-2 mt-1"><div class="bg-blue-500 rounded-full h-2" style="width: {s.position}%"></div></div>
                </div>
                <div>
                    <div class="flex justify-between text-sm text-gray-600"><span>Competitivo</span><span>{s.competitive:.0f}</span></div>
                    <div class="bg-gray-200 rounded-full h-2 mt-1"><div class="bg-blue-500 rounded-full h-2" style="width: {s.competitive}%"></div></div>
                </div>
            </div>
        </div>

        <!-- Verdicts Table -->
        <div class="bg-white rounded-2xl shadow-sm border mb-6 overflow-hidden">
            <div class="p-6 border-b">
                <h2 class="text-lg font-semibold text-gray-700">Resultados por Prompt</h2>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">#</th>
                            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Prompt</th>
                            <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Citado?</th>
                            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tipo</th>
                            <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Confiança</th>
                            <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase">Posição</th>
                            <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Concorrentes</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-gray-100">
                        {verdict_rows}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Competitors -->
        {"" if not competitor_cards else f'''
        <div class="mb-6">
            <h2 class="text-lg font-semibold text-gray-700 mb-4">Top Concorrentes</h2>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {competitor_cards}
            </div>
        </div>
        '''}

        <!-- Recommendations -->
        <div class="bg-white rounded-2xl shadow-sm border p-8 mb-6">
            <h2 class="text-lg font-semibold text-gray-700 mb-4">Plano de Ação</h2>
            <ol class="list-decimal list-inside text-gray-700 space-y-1">
                {rec_items}
            </ol>
        </div>

        <!-- Footer -->
        <div class="text-center text-xs text-gray-400 py-4">
            POC — iMedicina AI Visibility · Custo: ${report.metadata.total_cost_usd:.4f} ·
            Seed: {report.metadata.seed} · {report.metadata.generated_at.strftime('%Y-%m-%d')}
        </div>
    </div>
</body>
</html>"""

    path = output_dir / "report.html"
    path.write_text(html, encoding="utf-8")
    return path
