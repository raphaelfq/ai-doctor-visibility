"""Tests for the scorer — deterministic, no LLM calls.

Every expected value is hand-calculated.
2 dimensions: visibility (65%), dominance (35%).
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
        assert result.visibility == 100.0
        assert result.dominance == 100.0
        assert result.indirect_presence == 0.0
        assert result.overall == 100.0  # 0.65*100 + 0.35*100


class TestZeroScore:
    def test_all_dimensions_zero_or_near(self):
        verdicts = [
            make_verdict(f"p{i}", "not_mentioned") for i in range(1, 11)
        ]
        result = score(verdicts)
        assert result.visibility == 0.0
        # dominance: no active prompts = 0
        assert result.dominance == 0.0
        assert result.indirect_presence == 0.0
        # overall: 0.65*0 + 0.35*0 = 0
        assert result.overall == 0.0


class TestAllCompetitors:
    def test_competitive_zeroed(self):
        verdicts = [
            make_verdict(f"p{i}", "competitor_in_place", competitors_named=["Dr. Outro"])
            for i in range(1, 11)
        ]
        result = score(verdicts)
        assert result.visibility == 0.0
        assert result.dominance == 0.0
        assert result.indirect_presence == 0.0
        # overall: 0.65*0 + 0.35*0 = 0
        assert result.overall == 0.0


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

        # visibility: (100+90+80+15+15+0+0+0+0+0)/10 = 30.0
        assert result.visibility == 30.0
        # dominance: 3 by_name / (3 by_name + 0 competitor) = 100.0
        assert result.dominance == 100.0
        # indirect_presence: 2 mentioned_as_specialty / 10 = 20.0
        assert result.indirect_presence == 20.0
        # overall: 0.65*30 + 0.35*100 = 19.5 + 35 = 54.5
        assert result.overall == 54.5


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
        assert result.visibility == 0.0
        assert result.indirect_presence == 0.0
