"""Shared test fixtures."""

import pytest

from ai_visibility.models import Verdict


def make_verdict(
    prompt_id: str = "p1",
    citation_type: str = "not_mentioned",
    confidence: float = 1.0,
    position: int | None = None,
    evidence_quote: str = "test evidence",
    competitors_named: list[str] | None = None,
) -> Verdict:
    """Helper to create Verdict instances for tests."""
    return Verdict(
        prompt_id=prompt_id,
        citation_type=citation_type,
        confidence=confidence,
        position=position,
        evidence_quote=evidence_quote,
        competitors_named=competitors_named or [],
    )
