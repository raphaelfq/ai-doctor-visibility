"""Auto-register top competitor as a doctor after a pipeline run."""

from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter

from ai_visibility.models import Report
from ai_visibility.web.db import create_doctor, get_pool

logger = logging.getLogger(__name__)

# Patterns that suggest an entity is a clinic/institution, not a person
_CLINIC_PATTERNS = re.compile(
    r"\b(clínica|clinica|instituto|hospital|centro|lab|laboratório|laboratorio|"
    r"consultório|consultorio|unidade|rede|grupo|saúde|saude|medical|med\s|"
    r"dermatologia\b|pediatria\b|cardiologia\b|estética|estetica)\b",
    re.IGNORECASE,
)

# Pattern for a doctor name (starts with Dr./Dra. or has 2+ capitalized words)
_DOCTOR_NAME = re.compile(r"^(Dr\.?|Dra\.?)\s+\w", re.IGNORECASE)


def _is_likely_doctor(name: str) -> bool:
    """Heuristic: return True if the name looks like a person, not a clinic."""
    if _CLINIC_PATTERNS.search(name):
        return False
    if _DOCTOR_NAME.match(name):
        return True
    # Names with 2-4 capitalized words are likely people
    words = name.strip().split()
    if 2 <= len(words) <= 5 and all(w[0].isupper() for w in words if len(w) > 2):
        return True
    return False


def _find_top_competitor(report: Report) -> str | None:
    """Return the name of the most-cited competitor that looks like a doctor."""
    all_competitors: list[str] = []
    for v in report.verdicts:
        all_competitors.extend(v.competitors_named)

    if not all_competitors:
        return None

    for name, _count in Counter(all_competitors).most_common():
        if _is_likely_doctor(name):
            return name
    return None


def _already_registered(name: str) -> bool:
    """Check if a doctor with this name (case-insensitive) already exists."""
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM doctors WHERE lower(name) = lower(%s)", (name,)
        ).fetchone()
    return row is not None


async def _search_crm(doctor_name: str, specialty: str, city: str) -> dict[str, str | None]:
    """Use OpenAI web_search_preview to find a doctor's CRM number."""
    from openai import AsyncOpenAI
    from ai_visibility.config import settings

    client = AsyncOpenAI(api_key=settings.openai_api_key)

    query = f"CRM do médico {doctor_name} {specialty} {city} site:portal.cfm.org.br OR site:doctoralia.com.br"

    try:
        response = await client.responses.create(
            model=settings.model_simulator,
            tools=[{"type": "web_search_preview"}],
            input=query,
            temperature=0,
        )

        text = ""
        for item in response.output:
            if hasattr(item, "content"):
                for block in item.content:
                    if hasattr(block, "text"):
                        text += block.text

        # Try to extract CRM number
        crm_match = re.search(r"CRM[:\s/-]*(\d{4,7})[/\s-]*([A-Z]{2})?", text, re.IGNORECASE)
        if crm_match:
            return {
                "crm": crm_match.group(1),
                "crm_state": crm_match.group(2) if crm_match.group(2) else None,
            }

        # Try just a number after the state abbreviation pattern
        state_crm = re.search(r"(\d{4,7})\s*/?\s*(SP|RJ|MG|BA|PR|RS|SC|PE|CE|GO|DF|PA|MA|MT|MS|ES|PB|RN|AL|PI|SE|AM|RO|AC|AP|RR|TO)", text)
        if state_crm:
            return {"crm": state_crm.group(1), "crm_state": state_crm.group(2)}

        return {"crm": None, "crm_state": None}

    except Exception as e:
        logger.warning(f"CRM search failed for {doctor_name}: {e}")
        return {"crm": None, "crm_state": None}


def register_top_competitor(report: Report) -> str | None:
    """Find and register the top competitor from a completed run.

    Returns the new doctor_id if registered, None if skipped.
    """
    competitor_name = _find_top_competitor(report)
    if not competitor_name:
        logger.info("No doctor-like competitor found to register")
        return None

    if _already_registered(competitor_name):
        logger.info(f"Competitor '{competitor_name}' already registered, skipping")
        return None

    # Search for CRM
    specialty = report.doctor.specialty
    city = report.doctor.city
    state = report.doctor.state

    crm_info = asyncio.run(_search_crm(competitor_name, specialty, city))

    doctor_id = create_doctor(
        name=competitor_name,
        specialty=specialty,
        city=city,
        state=state,
        crm=crm_info.get("crm"),
        crm_state=crm_info.get("crm_state"),
    )

    logger.info(
        f"Registered competitor '{competitor_name}' as doctor "
        f"(id={doctor_id}, CRM={crm_info.get('crm')}/{crm_info.get('crm_state')})"
    )
    return doctor_id
