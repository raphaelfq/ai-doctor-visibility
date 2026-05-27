"""Unit tests for the judge stage — _derive_verdict decision tree."""

from ai_visibility.stages.judge import DecomposedEvaluation, _derive_verdict


class TestDeriveVerdictMentionedByName:
    def test_name_found_returns_mentioned_by_name(self):
        eval_result = DecomposedEvaluation(
            name_found=True,
            name_position=2,
            competitors_found=["Dr. Rival"],
            specialty_recommended=True,
            evidence_quote="Dr. Teste aparece na resposta",
        )
        verdict = _derive_verdict(eval_result, "p1")
        assert verdict.citation_type == "mentioned_by_name"
        assert verdict.confidence == 1.0
        assert verdict.position == 2
        assert verdict.competitors_named == ["Dr. Rival"]
        assert verdict.prompt_id == "p1"

    def test_name_found_without_competitors(self):
        eval_result = DecomposedEvaluation(
            name_found=True,
            name_position=1,
            competitors_found=[],
            specialty_recommended=False,
            evidence_quote="Dr. Teste em primeiro lugar",
        )
        verdict = _derive_verdict(eval_result, "p2")
        assert verdict.citation_type == "mentioned_by_name"
        assert verdict.confidence == 1.0
        assert verdict.position == 1
        assert verdict.competitors_named == []

    def test_name_found_takes_priority_over_all_other_flags(self):
        """name_found=True should always return mentioned_by_name regardless of other fields."""
        eval_result = DecomposedEvaluation(
            name_found=True,
            name_position=5,
            competitors_found=["Dr. A", "Dr. B"],
            specialty_recommended=True,
            evidence_quote="evidence",
        )
        verdict = _derive_verdict(eval_result, "p3")
        assert verdict.citation_type == "mentioned_by_name"


class TestDeriveVerdictCompetitorInPlace:
    def test_competitors_found_without_name(self):
        eval_result = DecomposedEvaluation(
            name_found=False,
            name_position=None,
            competitors_found=["Dr. Rival"],
            specialty_recommended=True,
            evidence_quote="Dr. Rival e recomendado",
        )
        verdict = _derive_verdict(eval_result, "p4")
        assert verdict.citation_type == "competitor_in_place"
        assert verdict.confidence == 0.95
        assert verdict.position is None
        assert verdict.competitors_named == ["Dr. Rival"]

    def test_multiple_competitors(self):
        eval_result = DecomposedEvaluation(
            name_found=False,
            name_position=None,
            competitors_found=["Dr. A", "Dr. B", "Clinica X"],
            specialty_recommended=False,
            evidence_quote="Varios concorrentes citados",
        )
        verdict = _derive_verdict(eval_result, "p5")
        assert verdict.citation_type == "competitor_in_place"
        assert len(verdict.competitors_named) == 3


class TestDeriveVerdictMentionedAsSpecialty:
    def test_specialty_recommended_no_competitors(self):
        eval_result = DecomposedEvaluation(
            name_found=False,
            name_position=None,
            competitors_found=[],
            specialty_recommended=True,
            evidence_quote="Procure dermatologista em Campinas",
        )
        verdict = _derive_verdict(eval_result, "p6")
        assert verdict.citation_type == "mentioned_as_specialty"
        assert verdict.confidence == 0.7
        assert verdict.position is None
        assert verdict.competitors_named == []


class TestDeriveVerdictNotMentioned:
    def test_nothing_found(self):
        eval_result = DecomposedEvaluation(
            name_found=False,
            name_position=None,
            competitors_found=[],
            specialty_recommended=False,
            evidence_quote="Resposta generica sem mencoes",
        )
        verdict = _derive_verdict(eval_result, "p7")
        assert verdict.citation_type == "not_mentioned"
        assert verdict.confidence == 0.9
        assert verdict.position is None
        assert verdict.competitors_named == []
