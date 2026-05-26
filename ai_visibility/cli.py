"""CLI interface using Typer."""

import asyncio
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ai_visibility.models import DoctorInput

app = typer.Typer(
    name="ai-visibility",
    help="AI Visibility diagnostic pipeline for medical professionals.",
)
console = Console()


@app.command()
def run(
    name: str = typer.Option(..., help="Nome completo do médico"),
    specialty: str = typer.Option(..., help="Especialidade (ex: Dermatologia)"),
    city: str = typer.Option(..., help="Cidade (ex: São Paulo)"),
    state: str = typer.Option(None, help="UF (ex: SP)"),
    neighborhood: str = typer.Option(None, help="Bairro (ex: Moema)"),
    crm: str = typer.Option(None, help="Número do CRM"),
    crm_state: str = typer.Option(None, "--crm-state", help="UF do CRM (ex: SP)"),
    doctor_file: Path = typer.Option(
        None, "--doctor", help="Caminho para JSON com dados do médico"
    ),
    output: Path = typer.Option(
        Path("./output"), help="Diretório de saída para os relatórios"
    ),
) -> None:
    """Executa o diagnóstico de visibilidade AI para um médico."""
    # Build DoctorInput from flags or JSON file
    if doctor_file and doctor_file.exists():
        data = json.loads(doctor_file.read_text())
        doctor = DoctorInput(**data)
    else:
        doctor = DoctorInput(
            name=name,
            specialty=specialty,
            city=city,
            state=state,
            neighborhood=neighborhood,
            crm=crm,
            crm_state=crm_state,
        )

    console.print(
        Panel(
            f"[bold]{doctor.name}[/bold]\n"
            f"{doctor.specialty} — {doctor.city}"
            + (f" ({doctor.neighborhood})" if doctor.neighborhood else "")
            + (f"\nCRM: {doctor.crm}/{doctor.crm_state}" if doctor.crm else ""),
            title="AI Visibility Diagnosis",
            border_style="blue",
        )
    )

    from ai_visibility.pipeline import run_pipeline
    from ai_visibility.report.html import render_html
    from ai_visibility.report.json_dump import dump_json
    from ai_visibility.report.markdown import render_markdown

    def on_progress(msg: str) -> None:
        console.print(f"  {msg}")

    report = asyncio.run(run_pipeline(doctor, output, on_progress=on_progress))

    # Generate all report formats
    dump_json(report, output)
    md_path = render_markdown(report, output)
    html_path = render_html(report, output)

    console.print()

    # Display summary table
    table = Table(title="Score Breakdown", show_header=True)
    table.add_column("Dimensão", style="bold")
    table.add_column("Score", justify="right")
    table.add_column("Peso", justify="right")

    table.add_row("Qualidade", f"{report.score.quality:.1f}", "25%")
    table.add_row("Presença", f"{report.score.presence:.1f}", "20%")
    table.add_row("Citation Strength", f"{report.score.citation_strength:.1f}", "15%")
    table.add_row("Share of Voice", f"{report.score.share_of_voice:.1f}", "15%")
    table.add_row("Posição", f"{report.score.position:.1f}", "10%")
    table.add_row("Sentiment", f"{report.score.sentiment:.1f}", "10%")
    table.add_row("Competitivo", f"{report.score.competitive:.1f}", "5%")
    table.add_row("", "", "")
    table.add_row("[bold]Overall[/bold]", f"[bold]{report.score.overall:.1f}[/bold]", "100%")
    console.print(table)

    # Display output paths
    console.print()
    console.print(f"[green]Relatórios gerados em:[/green] {output}")
    console.print(f"  report.html  → [blue]open {html_path}[/blue]")
    console.print(f"  report.md")
    console.print(f"  report.json")
    console.print(f"  trace.jsonl")


@app.command()
def report(
    data_dir: Path = typer.Argument(..., help="Diretório com report.json existente"),
) -> None:
    """Re-renderiza relatórios a partir de dados já gerados (sem reconsumir API)."""
    from ai_visibility.models import Report
    from ai_visibility.report.html import render_html
    from ai_visibility.report.markdown import render_markdown

    json_path = data_dir / "report.json"
    if not json_path.exists():
        console.print(f"[red]Erro:[/red] {json_path} não encontrado")
        raise typer.Exit(1)

    report_data = Report.model_validate_json(json_path.read_text())
    render_markdown(report_data, data_dir)
    render_html(report_data, data_dir)
    console.print(f"[green]Relatórios re-gerados em:[/green] {data_dir}")


@app.command()
def trace(
    data_dir: Path = typer.Argument(..., help="Diretório com trace.jsonl"),
    stage: str = typer.Option(None, help="Filtrar por estágio (generator, simulator, judge)"),
) -> None:
    """Inspeciona o trace de chamadas LLM."""
    trace_path = data_dir / "trace.jsonl"
    if not trace_path.exists():
        console.print(f"[red]Erro:[/red] {trace_path} não encontrado")
        raise typer.Exit(1)

    table = Table(title="LLM Trace", show_header=True)
    table.add_column("Stage")
    table.add_column("Prompt")
    table.add_column("Model")
    table.add_column("Tokens", justify="right")
    table.add_column("Latency", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Status")

    total_cost = 0.0
    for line in trace_path.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if stage and entry.get("stage") != stage:
            continue
        total_cost += entry.get("cost_usd", 0)
        table.add_row(
            entry.get("stage", ""),
            entry.get("prompt_id", "-"),
            entry.get("model", "")[-20:],
            f'{entry.get("tokens_in", 0)}→{entry.get("tokens_out", 0)}',
            f'{entry.get("latency_ms", 0)}ms',
            f'${entry.get("cost_usd", 0):.5f}',
            entry.get("status", ""),
        )

    console.print(table)
    console.print(f"\n[bold]Total cost:[/bold] ${total_cost:.4f}")
