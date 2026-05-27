"""CFM (Conselho Federal de Medicina) CRM validation.

Scrapes the public lookup at consultamedico.cfm.org.br to verify a doctor's
registration, status, and registered specialties (RQE).

Falls back gracefully: if the site blocks or times out, returns valid=None
so the pipeline can continue without CRM verification.
"""

import re

import httpx
from bs4 import BeautifulSoup

from ai_visibility.models import CFMValidation

_CFM_URL = "https://portal.cfm.org.br/busca-medicos/"
_TIMEOUT = 10.0


async def validate_crm(crm: str, crm_state: str) -> CFMValidation:
    """Validate a CRM number against the CFM public directory."""
    # Normalize CRM: remove dots, hyphens, spaces (e.g. "169.135" → "169135")
    crm = re.sub(r"[\s.\-/]", "", crm.strip())
    if not crm.isdigit():
        return CFMValidation(
            valid=False,
            error=f"CRM deve conter apenas dígitos, recebido: '{crm}'",
        )

    state = crm_state.strip().upper()
    if len(state) != 2:
        return CFMValidation(
            valid=False,
            error=f"UF deve ter 2 caracteres, recebido: '{crm_state}'",
        )

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            # The CFM portal uses a search form — attempt GET with query params
            response = await client.get(
                _CFM_URL,
                params={"inscricaoCrm": crm, "uf": state},
            )
            response.raise_for_status()
            return _parse_cfm_response(response.text)
    except Exception as e:
        # Fallback: format-only validation
        return CFMValidation(
            valid=None,
            error=f"Verificação CFM indisponível: {type(e).__name__}: {e}",
        )


def _parse_cfm_response(html: str) -> CFMValidation:
    """Extract doctor information from CFM search results page."""
    soup = BeautifulSoup(html, "html.parser")

    # Look for result cards — CFM portal renders cards with doctor info
    cards = soup.select(".card-body, .resultado-item, .busca-resultado")
    if not cards:
        # Try broader search for any doctor name pattern
        text = soup.get_text(separator=" ")
        if "Nenhum resultado" in text or "nenhum médico" in text.lower():
            return CFMValidation(valid=False, error="CRM não encontrado no CFM")

        # Page loaded but we can't parse the structure
        return CFMValidation(
            valid=None,
            error="Estrutura da página CFM não reconhecida — verificação pendente",
        )

    # Parse the first result card
    card_text = cards[0].get_text(separator="\n")

    # Extract name (usually the first bold/heading element)
    name_el = cards[0].select_one("h4, h3, .nome, strong")
    registered_name = name_el.get_text(strip=True) if name_el else None

    # Extract status
    status = None
    status_match = re.search(r"Situação[:\s]*(Ativo|Inativo|Cancelado)", card_text, re.IGNORECASE)
    if status_match:
        status = status_match.group(1).capitalize()

    # Extract specialties and RQE numbers
    specialties: list[str] = []
    rqe_numbers: list[str] = []
    rqe_matches = re.findall(r"RQE[:\s]*(\d+)", card_text)
    rqe_numbers = rqe_matches

    specialty_matches = re.findall(
        r"Especialidade[:\s]*([^\n\r]+)", card_text, re.IGNORECASE
    )
    specialties = [s.strip() for s in specialty_matches if s.strip()]

    return CFMValidation(
        valid=status is None or status == "Ativo",
        registered_name=registered_name,
        status=status,
        specialties=specialties,
        rqe_numbers=rqe_numbers,
    )
