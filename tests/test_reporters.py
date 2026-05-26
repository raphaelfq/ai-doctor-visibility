"""Tests for report generation — markdown, JSON, HTML."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ai_visibility.models import (
    DoctorInput,
    GeneratedPrompt,
    Report,
    ReportMetadata,
    ScoreBreakdown,
    SimulatedResponse,
    Verdict,
)
from ai_visibility.report.html import render_html
from ai_visibility.report.json_dump import dump_json
from ai_visibility.report.markdown import render_markdown


def _make_report() -> Report:
    """Create a minimal but complete Report for testing."""
    return Report(
        doctor=DoctorInput(
            name="Dr. Teste",
            specialty="Dermatologia",
            city="São Paulo",
            state="SP",
            crm="12345",
            crm_state="SP",
        ),
        prompts=[
            GeneratedPrompt(
                id="p1",
                text="Preciso de dermato em SP",
                persona="leigo_ansioso",
                intent_summary="Busca dermato genérico",
            ),
        ],
        responses=[
            SimulatedResponse(
                prompt_id="p1",
                raw_text="Recomendo Dr. Rival, excelente profissional.",
                model="gpt-4.1-mini",
                tokens_in=100,
                tokens_out=200,
                latency_ms=1500,
            ),
        ],
        verdicts=[
            Verdict(
                prompt_id="p1",
                citation_type="competitor_in_place",
                confidence=0.9,
                evidence_quote="Recomendo Dr. Rival",
                competitors_named=["Dr. Rival"],
            ),
        ],
        score=ScoreBreakdown(
            presence=0.0, quality=9.0, position=0.0, competitive=0.0, overall=3.6
        ),
        metadata=ReportMetadata(
            generated_at=datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc),
            model_generator="gpt-4.1-mini",
            model_simulator="gpt-4.1-mini",
            model_judge="gpt-4.1-mini",
            total_tokens_in=1000,
            total_tokens_out=500,
            total_cost_usd=0.05,
            seed=42,
        ),
    )


class TestJSONDump:
    def test_creates_valid_json(self):
        report = _make_report()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = dump_json(report, Path(tmpdir))
            assert path.exists()
            data = json.loads(path.read_text())
            assert data["doctor"]["name"] == "Dr. Teste"
            assert data["score"]["overall"] == 3.6

    def test_roundtrip(self):
        """JSON dump can be parsed back into a Report."""
        report = _make_report()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = dump_json(report, Path(tmpdir))
            restored = Report.model_validate_json(path.read_text())
            assert restored.score.overall == report.score.overall
            assert restored.doctor.name == report.doctor.name


class TestMarkdownReport:
    def test_creates_file(self):
        report = _make_report()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = render_markdown(report, Path(tmpdir))
            assert path.exists()
            content = path.read_text()
            assert "Dr. Teste" in content
            assert "3" in content or "3.6" in content  # score
            assert "Dermatologia" in content

    def test_contains_verdict_details(self):
        report = _make_report()
        with tempfile.TemporaryDirectory() as tmpdir:
            content = render_markdown(report, Path(tmpdir)).read_text()
            assert "competitor_in_place" in content
            assert "Dr. Rival" in content

    def test_contains_recommendations(self):
        report = _make_report()
        with tempfile.TemporaryDirectory() as tmpdir:
            content = render_markdown(report, Path(tmpdir)).read_text()
            assert "Plano de ação" in content


class TestHTMLReport:
    def test_creates_valid_html(self):
        report = _make_report()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = render_html(report, Path(tmpdir))
            assert path.exists()
            content = path.read_text()
            assert "<!DOCTYPE html>" in content
            assert "Dr. Teste" in content
            assert "tailwindcss" in content.lower() or "tailwind" in content.lower()

    def test_contains_svg_gauge(self):
        report = _make_report()
        with tempfile.TemporaryDirectory() as tmpdir:
            content = render_html(report, Path(tmpdir)).read_text()
            assert "<svg" in content
            assert "stroke-dasharray" in content

    def test_contains_verdict_table(self):
        report = _make_report()
        with tempfile.TemporaryDirectory() as tmpdir:
            content = render_html(report, Path(tmpdir)).read_text()
            assert "<table" in content
            assert "competitor" in content.lower()

    def test_responsive(self):
        """Check for viewport meta tag (mobile support)."""
        report = _make_report()
        with tempfile.TemporaryDirectory() as tmpdir:
            content = render_html(report, Path(tmpdir)).read_text()
            assert 'viewport' in content
