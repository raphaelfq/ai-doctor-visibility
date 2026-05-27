"""Tests for Pydantic model validation."""

import pytest
from pydantic import ValidationError

from ai_visibility.cfm import CFMValidation
from ai_visibility.models import (
    Citation,
    DoctorInput,
    GeneratedPrompt,
    ScoreBreakdown,
    SimulatedResponse,
    Verdict,
)


class TestDoctorInput:
    def test_minimal(self):
        doc = DoctorInput(name="Dr. Teste", specialty="Dermatologia", city="SP")
        assert doc.crm is None

    def test_full(self):
        doc = DoctorInput(
            name="Dra. Mariana Costa",
            specialty="Dermatologia",
            city="São Paulo",
            state="SP",
            neighborhood="Moema",
            crm="54321",
            crm_state="SP",
        )
        assert doc.crm == "54321"


class TestVerdict:
    def test_valid(self):
        v = Verdict(
            prompt_id="p1",
            citation_type="mentioned_by_name",
            confidence=0.95,
            position=1,
            evidence_quote="Dr. Fulano é referência",
        )
        assert v.position == 1

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            Verdict(
                prompt_id="p1",
                citation_type="not_mentioned",
                confidence=1.5,  # > 1.0
                evidence_quote="test",
            )

        with pytest.raises(ValidationError):
            Verdict(
                prompt_id="p1",
                citation_type="not_mentioned",
                confidence=-0.1,  # < 0.0
                evidence_quote="test",
            )

    def test_position_must_be_positive(self):
        with pytest.raises(ValidationError):
            Verdict(
                prompt_id="p1",
                citation_type="mentioned_by_name",
                confidence=0.9,
                position=0,  # < 1
                evidence_quote="test",
            )

    def test_invalid_citation_type(self):
        with pytest.raises(ValidationError):
            Verdict(
                prompt_id="p1",
                citation_type="invalid_type",
                confidence=0.5,
                evidence_quote="test",
            )


class TestScoreBreakdown:
    def test_valid_scores(self):
        s = ScoreBreakdown(
            visibility=50.0, dominance=80.0, indirect_presence=10.0, overall=42.0,
        )
        assert s.overall == 42.0
        assert s.indirect_presence == 10.0

    def test_score_bounds(self):
        with pytest.raises(ValidationError):
            ScoreBreakdown(
                visibility=101.0,  # > 100
                dominance=0.0,
                indirect_presence=0.0,
                overall=0.0,
            )

        with pytest.raises(ValidationError):
            ScoreBreakdown(
                visibility=-1.0,  # < 0
                dominance=0.0,
                indirect_presence=0.0,
                overall=0.0,
            )


class TestGeneratedPrompt:
    def test_valid_persona(self):
        p = GeneratedPrompt(
            id="p1",
            text="Preciso de dermato",
            persona="leigo_ansioso",
            intent_summary="Busca dermato",
        )
        assert p.persona == "leigo_ansioso"

    def test_invalid_persona(self):
        with pytest.raises(ValidationError):
            GeneratedPrompt(
                id="p1",
                text="test",
                persona="invalid_persona",
                intent_summary="test",
            )


class TestCFMValidation:
    def test_defaults(self):
        cfm = CFMValidation()
        assert cfm.valid is None
        assert cfm.specialties == []

    def test_valid_doctor(self):
        cfm = CFMValidation(
            valid=True,
            registered_name="Dr. Teste",
            status="Ativo",
            specialties=["Dermatologia"],
            rqe_numbers=["12345"],
        )
        assert cfm.valid is True
