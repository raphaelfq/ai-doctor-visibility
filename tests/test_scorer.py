"""Tests for the scorer — deterministic, no LLM calls.

Every expected value is hand-calculated.
V4: 7 dimensions (4 original + citation_strength + share_of_voice + sentiment).
"""

import pytest

from ai_visibility.models import Citation, SimulatedResponse
from ai_visibility.stages.scorer import (
    citation_strength,
    score,
    sentiment_score,
    share_of_voice,
)
from tests.conftest import make_verdict


def _make_response(prompt_id: str, raw_text: str = "test", citations=None):
    return SimulatedResponse(
        prompt_id=prompt_id,
        raw_text=raw_text,
        model="test",
        tokens_in=0,
        tokens_out=0,
        latency_ms=0,
        citations=citations or [],
    )


# ---------------------------------------------------------------------------
# Core dimensions (kept from V3)
# ---------------------------------------------------------------------------


class TestPerfectScore:
    def test_all_dimensions_maxed(self):
        verdicts = [
            make_verdict(f"p{i}", "mentioned_by_name", 1.0, position=1)
            for i in range(1, 11)
        ]
        responses = [
            _make_response(
                f"p{i}",
                raw_text="Dr. Teste, especialista renomado. 5.0 (30 avaliações). Rua X, 04535-001.",
                citations=[
                    Citation(url="https://drteste.com.br", title="Dr. Teste"),
                    Citation(url="https://google.com/maps/search/Dr.+Teste", title="Dr. Teste"),
                    Citation(url="https://doctoralia.com.br/teste", title="Dr. Teste"),
                ],
            )
            for i in range(1, 11)
        ]
        result = score(verdicts, responses=responses, doctor_name="Dr. Teste")

        assert result.presence == 100.0
        assert result.quality == 100.0
        assert result.position == 100.0
        assert result.competitive == 100.0
        assert result.citation_strength == 100.0
        assert result.share_of_voice == 100.0
        assert result.sentiment == 100.0
        assert result.overall == 100.0


class TestZeroScore:
    def test_all_dimensions_zero_or_near(self):
        verdicts = [
            make_verdict(f"p{i}", "not_mentioned") for i in range(1, 11)
        ]
        responses = [_make_response(f"p{i}") for i in range(1, 11)]
        result = score(verdicts, responses=responses, doctor_name="Dr. Ninguem")

        assert result.presence == 0.0
        assert result.quality == 0.0
        assert result.position == 0.0
        assert result.citation_strength == 0.0
        assert result.share_of_voice == 0.0
        assert result.sentiment == 0.0
        # competitive: no competitors = 100
        assert result.competitive == 100.0
        # overall: only competitive contributes: 0.05 * 100 = 5.0
        assert result.overall == 5.0


class TestAllCompetitors:
    def test_competitive_zeroed(self):
        verdicts = [
            make_verdict(f"p{i}", "competitor_in_place", competitors_named=["Dr. Outro"])
            for i in range(1, 11)
        ]
        responses = [_make_response(f"p{i}") for i in range(1, 11)]
        result = score(verdicts, responses=responses, doctor_name="Dr. Ninguem")

        assert result.presence == 0.0
        assert result.competitive == 0.0
        # share_of_voice: 0 doctor mentions / 10 competitor mentions = 0%
        assert result.share_of_voice == 0.0


class TestMixedResults:
    def test_intermediate_score(self):
        verdicts = [
            make_verdict("p1", "mentioned_by_name", 0.95, position=1),
            make_verdict("p2", "mentioned_by_name", 0.90, position=2),
            make_verdict("p3", "mentioned_by_name", 0.85, position=3),
            make_verdict("p4", "mentioned_as_specialty", 0.80),
            make_verdict("p5", "mentioned_as_specialty", 0.75),
            make_verdict("p6", "not_mentioned", 1.0),
            make_verdict("p7", "not_mentioned", 1.0),
            make_verdict("p8", "not_mentioned", 1.0),
            make_verdict("p9", "not_mentioned", 1.0),
            make_verdict("p10", "not_mentioned", 1.0),
        ]
        responses = [_make_response(f"p{i}") for i in range(1, 11)]
        result = score(verdicts, responses=responses, doctor_name="Dr. Teste")

        assert result.presence == 50.0
        # quality: (100*0.95 + 100*0.90 + 100*0.85 + 30*0.80 + 30*0.75) / 10 = 31.65 → 31.6
        assert result.quality == pytest.approx(31.6, abs=0.1)
        # position: (100 + 90 + 80) / 3 = 90.0
        assert result.position == 90.0
        assert result.competitive == 100.0
        # share_of_voice: 3 by_name / (3 + 0 competitors) = 100%
        assert result.share_of_voice == 100.0


class TestReproducibility:
    def test_identical_runs(self):
        verdicts = [
            make_verdict("p1", "mentioned_by_name", 0.9, position=2),
            make_verdict("p2", "competitor_in_place", 0.8, competitors_named=["Dr. X"]),
            make_verdict("p3", "not_mentioned", 1.0),
        ]
        responses = [_make_response(f"p{i}") for i in range(1, 4)]
        r1 = score(verdicts, responses=responses, doctor_name="Dr. T")
        r2 = score(verdicts, responses=responses, doctor_name="Dr. T")

        assert r1.overall == r2.overall


class TestEmptyInput:
    def test_returns_zeros(self):
        result = score([])
        assert result.overall == 0.0
        assert result.citation_strength == 0.0
        assert result.share_of_voice == 0.0
        assert result.sentiment == 0.0


class TestBackwardsCompatibility:
    """Score function works without responses (V3 mode)."""

    def test_without_responses(self):
        verdicts = [
            make_verdict("p1", "mentioned_by_name", 1.0, position=1),
            make_verdict("p2", "not_mentioned", 1.0),
        ]
        result = score(verdicts)
        assert result.presence == 50.0
        assert result.citation_strength == 0.0  # no responses → 0
        assert result.sentiment == 0.0


# ---------------------------------------------------------------------------
# New dimensions (V4)
# ---------------------------------------------------------------------------


class TestCitationStrength:
    def test_own_site_cited(self):
        responses = [
            _make_response("p1", citations=[
                Citation(url="https://drjoao.com.br/page", title="Dr. João Silva"),
            ]),
        ]
        result = citation_strength(responses, "Dr. João Silva")
        # own_site=40 + 1 source=10 = 50
        assert result == 50.0

    def test_google_maps(self):
        responses = [
            _make_response("p1", citations=[
                Citation(url="https://google.com/maps/search/Dr.+Joao", title="Dr. João"),
                Citation(url="https://drjoao.com.br", title="Dr. João"),
            ]),
        ]
        result = citation_strength(responses, "Dr. João")
        # own_site=40 + maps=25 + 2 sources ≥1 = 10 → 75
        assert result == 75.0

    def test_no_citations(self):
        responses = [_make_response("p1")]
        assert citation_strength(responses, "Dr. Ninguem") == 0.0

    def test_competitor_citations_dont_count(self):
        responses = [
            _make_response("p1", citations=[
                Citation(url="https://draoutro.com.br", title="Dra. Outro"),
            ]),
        ]
        result = citation_strength(responses, "Dr. João")
        assert result == 0.0


class TestShareOfVoice:
    def test_all_doctor_mentions(self):
        verdicts = [
            make_verdict("p1", "mentioned_by_name"),
            make_verdict("p2", "mentioned_by_name"),
        ]
        assert share_of_voice(verdicts) == 100.0

    def test_no_mentions_at_all(self):
        verdicts = [make_verdict("p1", "not_mentioned")]
        assert share_of_voice(verdicts) == 0.0

    def test_shared_with_competitors(self):
        verdicts = [
            make_verdict("p1", "mentioned_by_name", competitors_named=["Dr. A"]),
            make_verdict("p2", "competitor_in_place", competitors_named=["Dr. A", "Dr. B"]),
        ]
        # doctor: 1 mention, competitors: 1 + 2 = 3, total = 4
        assert share_of_voice(verdicts) == pytest.approx(25.0)


class TestSentimentScore:
    def test_rich_mention(self):
        verdicts = [make_verdict("p1", "mentioned_by_name")]
        responses = [
            _make_response(
                "p1",
                raw_text="Dr. João, especialista renomado. 5.0 (30 avaliações). Rua X, 04535-001.",
            ),
        ]
        result = sentiment_score(responses, verdicts)
        # rating=30 + cep=20 + especialista=25 + renomado=25 = 100
        assert result == 100.0

    def test_bare_mention(self):
        verdicts = [make_verdict("p1", "mentioned_by_name")]
        responses = [_make_response("p1", raw_text="Dr. João atende em Campinas.")]
        result = sentiment_score(responses, verdicts)
        assert result == 0.0  # no rating, no cep, no keywords

    def test_not_mentioned_returns_zero(self):
        verdicts = [make_verdict("p1", "not_mentioned")]
        responses = [_make_response("p1")]
        assert sentiment_score(responses, verdicts) == 0.0
