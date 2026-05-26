"""Tests for the scorer — deterministic, no LLM calls.

Every expected value is hand-calculated.
4 dimensions: quality (40%), presence (30%), position (20%), competitive (10%).
"""

import pytest

from ai_visibility.stages.scorer import score
from tests.conftest import make_verdict


class TestPerfectScore:
    def test_all_dimensions_maxed(self):
        verdicts = [
            make_verdict(f"p{i}", "mentioned_by_name", 1.0, position=1)
            for i in range(1, 11)
        ]
        result = score(verdicts)
        assert result.presence == 100.0
        assert result.quality == 100.0
        assert result.position == 100.0
        assert result.competitive == 100.0
        assert result.overall == 100.0


class TestZeroScore:
    def test_all_dimensions_zero_or_near(self):
        verdicts = [
            make_verdict(f"p{i}", "not_mentioned") for i in range(1, 11)
        ]
        result = score(verdicts)
        assert result.presence == 0.0
        assert result.quality == 0.0
        assert result.position == 0.0
        # competitive: no competitors = 100
        assert result.competitive == 100.0
        # overall: 0.40*0 + 0.30*0 + 0.20*0 + 0.10*100 = 10
        assert result.overall == 10.0


class TestAllCompetitors:
    def test_competitive_zeroed(self):
        verdicts = [
            make_verdict(f"p{i}", "competitor_in_place", competitors_named=["Dr. Outro"])
            for i in range(1, 11)
        ]
        result = score(verdicts)
        assert result.presence == 0.0
        # quality: 10 * 1.0 / 10 = 10
        assert result.quality == 10.0
        assert result.position == 0.0
        assert result.competitive == 0.0
        # overall: 0.40*10 + 0.30*0 + 0.20*0 + 0.10*0 = 4
        assert result.overall == 4.0


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
        result = score(verdicts)

        assert result.presence == 50.0
        assert result.quality == pytest.approx(31.6, abs=0.1)
        assert result.position == 90.0
        assert result.competitive == 100.0
        # 0.40*31.65 + 0.30*50 + 0.20*90 + 0.10*100 = 55.66 → 55.7
        assert result.overall == pytest.approx(55.7, abs=0.1)


class TestReproducibility:
    def test_identical_runs(self):
        verdicts = [
            make_verdict("p1", "mentioned_by_name", 0.9, position=2),
            make_verdict("p2", "competitor_in_place", 0.8, competitors_named=["Dr. X"]),
            make_verdict("p3", "not_mentioned", 1.0),
        ]
        r1 = score(verdicts)
        r2 = score(verdicts)
        assert r1.overall == r2.overall


class TestEmptyInput:
    def test_returns_zeros(self):
        result = score([])
        assert result.overall == 0.0
        assert result.presence == 0.0
