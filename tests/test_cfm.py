"""Tests for CFM validation — tests the parser and format validation only (no HTTP)."""

import pytest

from ai_visibility.cfm import _parse_cfm_response, validate_crm
from ai_visibility.cfm import CFMValidation


class TestCRMFormatValidation:
    """Tests that run validate_crm with invalid formats (no HTTP call needed)."""

    @pytest.mark.asyncio
    async def test_non_numeric_crm(self):
        result = await validate_crm("abc123", "SP")
        assert result.valid is False
        assert "dígitos" in result.error

    @pytest.mark.asyncio
    async def test_invalid_state_length(self):
        result = await validate_crm("12345", "SPA")
        assert result.valid is False
        assert "2 caracteres" in result.error

    @pytest.mark.asyncio
    async def test_empty_crm(self):
        result = await validate_crm("", "SP")
        assert result.valid is False


class TestCFMHTMLParser:
    """Tests the HTML parser with synthetic HTML."""

    def test_no_results_page(self):
        html = "<html><body><p>Nenhum resultado encontrado</p></body></html>"
        result = _parse_cfm_response(html)
        assert result.valid is False
        assert "não encontrado" in result.error

    def test_unrecognised_structure(self):
        html = "<html><body><p>Algum conteúdo aleatório</p></body></html>"
        result = _parse_cfm_response(html)
        assert result.valid is None  # Can't determine
        assert "não reconhecida" in result.error

    def test_card_with_active_doctor(self):
        html = """
        <html><body>
        <div class="card-body">
            <h4>Dr. João da Silva</h4>
            <p>Situação: Ativo</p>
            <p>Especialidade: Dermatologia</p>
            <p>RQE: 67890</p>
        </div>
        </body></html>
        """
        result = _parse_cfm_response(html)
        assert result.valid is True
        assert result.registered_name == "Dr. João da Silva"
        assert result.status == "Ativo"
        assert "67890" in result.rqe_numbers

    def test_card_with_inactive_doctor(self):
        html = """
        <html><body>
        <div class="card-body">
            <h4>Dr. Inativo</h4>
            <p>Situação: Inativo</p>
        </div>
        </body></html>
        """
        result = _parse_cfm_response(html)
        assert result.valid is False
        assert result.status == "Inativo"
