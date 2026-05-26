"""Tests for recommendation generation logic."""

from ai_visibility.models import ScoreBreakdown, Verdict
from ai_visibility.stages.scorer import generate_recommendations
from tests.conftest import make_verdict


class TestInvisibleDoctor:
    """Doctor with near-zero visibility."""

    def test_invisibility_warning(self):
        verdicts = [
            make_verdict(f"p{i}", "not_mentioned") for i in range(1, 11)
        ]
        score = ScoreBreakdown(
            presence=0.0, quality=0.0, position=0.0, competitive=100.0,
            citation_strength=0.0, share_of_voice=0.0, sentiment=0.0, overall=10.0,
        )
        recs = generate_recommendations(verdicts, score, "Dr. Teste", "Dermatologia")

        assert any("invisível" in r.lower() for r in recs)
        assert any("entidade" in r.lower() or "construa" in r.lower() for r in recs)


class TestCompetitorDominance:
    """Doctor displaced by a dominant competitor."""

    def test_names_top_competitor(self):
        verdicts = [
            make_verdict(
                f"p{i}",
                "competitor_in_place",
                competitors_named=["Dr. Rival"],
            )
            for i in range(1, 9)
        ] + [
            make_verdict("p9", "not_mentioned"),
            make_verdict("p10", "not_mentioned"),
        ]
        score = ScoreBreakdown(
            presence=0.0, quality=8.0, position=0.0, competitive=20.0,
            citation_strength=0.0, share_of_voice=0.0, sentiment=0.0, overall=5.2,
        )
        recs = generate_recommendations(verdicts, score, "Dr. Teste", "Dermatologia")

        assert any("Dr. Rival" in r for r in recs)


class TestAboveBenchmark:
    """Doctor with good visibility above specialty average."""

    def test_positive_message(self):
        verdicts = [
            make_verdict(f"p{i}", "mentioned_by_name", position=1)
            for i in range(1, 11)
        ]
        score = ScoreBreakdown(
            presence=100.0, quality=100.0, position=100.0, competitive=100.0,
            citation_strength=100.0, share_of_voice=100.0, sentiment=100.0, overall=100.0,
        )
        recs = generate_recommendations(verdicts, score, "Dr. Teste", "Dermatologia")

        assert any("acima" in r.lower() or "boa" in r.lower() for r in recs)


class TestBelowBenchmark:
    """Doctor below specialty average."""

    def test_benchmark_comparison(self):
        verdicts = [
            make_verdict("p1", "mentioned_by_name", position=3),
            *[make_verdict(f"p{i}", "not_mentioned") for i in range(2, 11)],
        ]
        score = ScoreBreakdown(
            presence=10.0, quality=10.0, position=80.0, competitive=100.0,
            citation_strength=0.0, share_of_voice=0.0, sentiment=0.0, overall=24.0,
        )
        recs = generate_recommendations(verdicts, score, "Dr. Teste", "Dermatologia")

        # Dermatologia benchmark is 35, score is 24 → should warn
        assert any("abaixo" in r.lower() or "média" in r.lower() for r in recs)


class TestAlwaysReturnsAtLeastOne:
    def test_never_empty(self):
        verdicts = [make_verdict("p1", "not_mentioned")]
        score = ScoreBreakdown(
            presence=0.0, quality=0.0, position=0.0, competitive=100.0,
            citation_strength=0.0, share_of_voice=0.0, sentiment=0.0, overall=10.0,
        )
        recs = generate_recommendations(verdicts, score, "Dr. Teste", "Cardiologia")
        assert len(recs) >= 1
