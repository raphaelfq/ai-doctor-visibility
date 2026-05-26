"""Tests for the scorer — deterministic, no LLM calls.

Every expected value is hand-calculated. These tests MUST fail
if the scoring formula changes unexpectedly.
"""

import pytest

from ai_visibility.stages.scorer import score
from tests.conftest import make_verdict


class TestPerfectScore:
    """All prompts: mentioned_by_name, confidence 1.0, position 1."""

    def test_all_dimensions_maxed(self):
        verdicts = [
            make_verdict(
                prompt_id=f"p{i}",
                citation_type="mentioned_by_name",
                confidence=1.0,
                position=1,
            )
            for i in range(1, 11)
        ]
        result = score(verdicts)

        assert result.presence == 100.0
        assert result.quality == 100.0
        # position: (11-1)*10 = 100 for each
        assert result.position == 100.0
        # no competitors
        assert result.competitive == 100.0
        # overall: 0.40*100 + 0.30*100 + 0.20*100 + 0.10*100 = 100
        assert result.overall == 100.0


class TestZeroScore:
    """All prompts: not_mentioned."""

    def test_all_dimensions_zero_or_near(self):
        verdicts = [
            make_verdict(prompt_id=f"p{i}", citation_type="not_mentioned")
            for i in range(1, 11)
        ]
        result = score(verdicts)

        assert result.presence == 0.0
        assert result.quality == 0.0
        assert result.position == 0.0
        # competitive: 100 - 0% competitor = 100
        assert result.competitive == 100.0
        # overall: 0.40*0 + 0.30*0 + 0.20*0 + 0.10*100 = 10
        assert result.overall == 10.0


class TestAllCompetitors:
    """All prompts: competitor_in_place."""

    def test_competitive_zeroed(self):
        verdicts = [
            make_verdict(
                prompt_id=f"p{i}",
                citation_type="competitor_in_place",
                competitors_named=["Dr. Outro"],
            )
            for i in range(1, 11)
        ]
        result = score(verdicts)

        # presence: competitor_in_place is NOT counted as "appeared"
        assert result.presence == 0.0
        # quality: competitor_in_place = 10 * 1.0 / 10 = 10
        assert result.quality == 10.0
        assert result.position == 0.0
        # competitive: 100 - 100% = 0
        assert result.competitive == 0.0
        # overall: 0.40*10 + 0.30*0 + 0.20*0 + 0.10*0 = 4
        assert result.overall == 4.0


class TestMixedResults:
    """Realistic mix: 3 mentioned_by_name, 2 mentioned_as_specialty, 5 not_mentioned."""

    def test_intermediate_score(self):
        verdicts = [
            # 3 mentioned by name at positions 1, 2, 3
            make_verdict("p1", "mentioned_by_name", 0.95, position=1),
            make_verdict("p2", "mentioned_by_name", 0.90, position=2),
            make_verdict("p3", "mentioned_by_name", 0.85, position=3),
            # 2 mentioned as specialty
            make_verdict("p4", "mentioned_as_specialty", 0.80),
            make_verdict("p5", "mentioned_as_specialty", 0.75),
            # 5 not mentioned
            make_verdict("p6", "not_mentioned", 1.0),
            make_verdict("p7", "not_mentioned", 1.0),
            make_verdict("p8", "not_mentioned", 1.0),
            make_verdict("p9", "not_mentioned", 1.0),
            make_verdict("p10", "not_mentioned", 1.0),
        ]
        result = score(verdicts)

        # presence: 5 mentioned (3 by_name + 2 as_specialty) / 10 = 50%
        assert result.presence == 50.0

        # quality: (100*0.95 + 100*0.90 + 100*0.85 + 30*0.80 + 30*0.75 + 0*5) / 10
        # = (95 + 90 + 85 + 24 + 22.5) / 10 = 316.5 / 10 = 31.65
        assert result.quality == 31.6  # rounded to 1 decimal

        # position: avg of (11-1)*10=100, (11-2)*10=90, (11-3)*10=80 = 270/3 = 90
        assert result.position == 90.0

        # competitive: no competitor_in_place, so 100
        assert result.competitive == 100.0

        # overall uses unrounded intermediates:
        # 0.40*31.65 + 0.30*50 + 0.20*90 + 0.10*100
        # = 12.66 + 15 + 18 + 10 = 55.66 → rounds to 55.7
        assert result.overall == pytest.approx(55.7, abs=0.1)


class TestReproducibility:
    """Same input → same output (deterministic)."""

    def test_identical_runs(self):
        verdicts = [
            make_verdict("p1", "mentioned_by_name", 0.9, position=2),
            make_verdict("p2", "competitor_in_place", 0.8, competitors_named=["Dr. X"]),
            make_verdict("p3", "not_mentioned", 1.0),
        ]
        result1 = score(verdicts)
        result2 = score(verdicts)

        assert result1.overall == result2.overall
        assert result1.presence == result2.presence
        assert result1.quality == result2.quality
        assert result1.position == result2.position
        assert result1.competitive == result2.competitive


class TestEmptyInput:
    """Edge case: no verdicts."""

    def test_returns_zeros(self):
        result = score([])
        assert result.overall == 0.0
        assert result.presence == 0.0
