"""Tests for LLM client utilities — cost estimation, tracing, and error paths."""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from ai_visibility.llm import LLMClient, _estimate_cost, WEB_SEARCH_COST_PER_CALL


class TestCostEstimation:
    def test_gpt41_mini_known_model(self):
        # gpt-4.1-mini: $0.40/1M input, $1.60/1M output
        cost = _estimate_cost("gpt-4.1-mini", tokens_in=1000, tokens_out=500)
        expected = (1000 * 0.40 + 500 * 1.60) / 1_000_000
        assert abs(cost - expected) < 1e-9

    def test_gpt41_full_model(self):
        # gpt-4.1: $2.00/1M input, $8.00/1M output
        cost = _estimate_cost("gpt-4.1", tokens_in=1000, tokens_out=500)
        expected = (1000 * 2.00 + 500 * 8.00) / 1_000_000
        assert abs(cost - expected) < 1e-9

    def test_unknown_model_uses_default(self):
        cost = _estimate_cost("unknown-model", tokens_in=1000, tokens_out=500)
        # Falls back to mini rates
        expected = (1000 * 0.40 + 500 * 1.60) / 1_000_000
        assert abs(cost - expected) < 1e-9

    def test_zero_tokens(self):
        assert _estimate_cost("gpt-4.1-mini", 0, 0) == 0.0

    def test_web_search_cost_constant(self):
        assert WEB_SEARCH_COST_PER_CALL == 0.01


class TestGenerateStructuredTimeout:
    @pytest.mark.asyncio
    async def test_timeout_logs_trace_and_reraises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "trace.jsonl"
            client = LLMClient(trace_path=trace_path)

            client._client.responses = AsyncMock()
            client._client.responses.parse = AsyncMock(
                side_effect=asyncio.TimeoutError()
            )

            with pytest.raises(asyncio.TimeoutError):
                await client.generate_structured(
                    model="gpt-4.1-mini",
                    input=[{"role": "user", "content": "test"}],
                    text_format=type("Dummy", (), {}),
                    temperature=0,
                    stage="test",
                    prompt_id="p1",
                )

            lines = trace_path.read_text().splitlines()
            assert len(lines) == 1
            entry = json.loads(lines[0])
            assert entry["status"] == "timeout"
            assert entry["stage"] == "test"
            assert "timed out" in entry["error"]


class TestGenerateStructuredGenericError:
    @pytest.mark.asyncio
    async def test_generic_error_logs_trace_and_reraises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "trace.jsonl"
            client = LLMClient(trace_path=trace_path)

            client._client.responses = AsyncMock()
            client._client.responses.parse = AsyncMock(
                side_effect=RuntimeError("API connection failed")
            )

            with pytest.raises(RuntimeError, match="API connection failed"):
                await client.generate_structured(
                    model="gpt-4.1-mini",
                    input=[{"role": "user", "content": "test"}],
                    text_format=type("Dummy", (), {}),
                    temperature=0,
                    stage="test",
                    prompt_id="p2",
                )

            lines = trace_path.read_text().splitlines()
            assert len(lines) == 1
            entry = json.loads(lines[0])
            assert entry["status"] == "error"
            assert "API connection failed" in entry["error"]


class TestSearchTimeout:
    @pytest.mark.asyncio
    async def test_search_timeout_logs_trace_and_reraises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_path = Path(tmpdir) / "trace.jsonl"
            client = LLMClient(trace_path=trace_path)

            client._client.responses = AsyncMock()
            client._client.responses.create = AsyncMock(
                side_effect=asyncio.TimeoutError()
            )

            with pytest.raises(asyncio.TimeoutError):
                await client.search(
                    model="gpt-4.1-mini",
                    input="test query",
                    stage="simulator",
                    prompt_id="p3",
                )

            lines = trace_path.read_text().splitlines()
            assert len(lines) == 1
            entry = json.loads(lines[0])
            assert entry["status"] == "timeout"
            assert entry["stage"] == "simulator"


class TestFullDiagnosisCostEstimate:
    """Estimate total cost for a full diagnosis run (10 prompts)."""

    def test_estimated_cost_under_20_cents(self):
        # Generator: 1 call, ~300 tokens in, ~1000 tokens out
        gen_cost = _estimate_cost("gpt-4.1-mini", 300, 1000)

        # Simulator: 10 calls with web search
        sim_token_cost = 10 * _estimate_cost("gpt-4.1-mini", 200, 600)
        sim_search_cost = 10 * WEB_SEARCH_COST_PER_CALL

        # Judge: 10 calls
        judge_cost = 10 * _estimate_cost("gpt-4.1-mini", 800, 200)

        total = gen_cost + sim_token_cost + sim_search_cost + judge_cost

        # Should be well under $0.20
        assert total < 0.20
        # Should be around $0.10-0.15
        assert total > 0.01
