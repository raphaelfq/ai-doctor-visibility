"""Centralised OpenAI client with tracing and rate-limit protection.

Design (from PRACTICES §3 and §5):
- AsyncOpenAI with max_retries (SDK handles 429 backoff)
- asyncio.Semaphore to cap concurrent calls
- Every LLM call logged to trace.jsonl
- Langfuse integration: drop-in AsyncOpenAI wrapper captures all calls
  automatically (tokens, cost, latency, inputs/outputs) → Langfuse dashboard
"""

import asyncio
import json
import logging
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import dotenv

# Suppress Pydantic serialization warnings from Langfuse internals
warnings.filterwarnings("ignore", message=".*PydanticSerializationUnexpectedValue.*")

# Load .env into os.environ BEFORE importing langfuse (it reads env vars directly)
dotenv.load_dotenv()

from pydantic import ValidationError

from langfuse.openai import AsyncOpenAI

from ai_visibility.config import settings
from ai_visibility.models import TraceEntry

logger = logging.getLogger(__name__)

# Pricing per 1M tokens (May 2026)
MODEL_COST: dict[str, dict[str, float]] = {
    "gpt-4.1-mini-2025-04-14": {"input": 0.40, "output": 1.60},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-2025-04-14": {"input": 2.00, "output": 8.00},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
}

# Cost per web_search_preview call
WEB_SEARCH_COST_PER_CALL = 0.01


def _estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    rates = MODEL_COST.get(model, {"input": 0.40, "output": 1.60})
    return (tokens_in * rates["input"] + tokens_out * rates["output"]) / 1_000_000


class LLMClient:
    """Async OpenAI wrapper with concurrency control and trace logging."""

    def __init__(self, trace_path: Path | None = None):
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            max_retries=settings.max_retries,
        )
        self._semaphore = asyncio.Semaphore(settings.semaphore_limit)
        self._timeout = settings.llm_timeout_seconds
        self._trace_path = trace_path

    async def generate_structured(
        self,
        *,
        model: str,
        input: list[dict],
        text_format: type,
        temperature: float,
        stage: str,
        prompt_id: str | None = None,
        seed: int | None = None,
    ):
        """Call Responses API with structured output (client.responses.parse).

        Separates HTTP call from JSON parsing so that:
        - Timeouts only apply to the network call
        - Parse failures (truncated/empty JSON) still log token usage
        """
        async with self._semaphore:
            start = time.monotonic()
            try:
                response = await asyncio.wait_for(
                    self._client.responses.parse(
                        model=model,
                        input=input,
                        text_format=text_format,
                        temperature=temperature,
                    ),
                    timeout=self._timeout,
                )
                latency_ms = int((time.monotonic() - start) * 1000)

                tokens_in = response.usage.input_tokens if response.usage else 0
                tokens_out = response.usage.output_tokens if response.usage else 0

                self._log_trace(
                    stage=stage,
                    prompt_id=prompt_id,
                    model=model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=latency_ms,
                    status="success",
                )
                return response
            except ValidationError as e:
                # Model returned invalid/empty JSON — response was received
                # but Pydantic could not parse it. Log and re-raise so the
                # caller (judge) can retry.
                latency_ms = int((time.monotonic() - start) * 1000)
                logger.warning(
                    "Structured output parse failed for %s/%s (%dms): %s",
                    stage, prompt_id, latency_ms, e,
                )
                self._log_trace(
                    stage=stage,
                    prompt_id=prompt_id,
                    model=model,
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=latency_ms,
                    status="parse_error",
                    error=str(e),
                )
                raise
            except asyncio.TimeoutError:
                latency_ms = int((time.monotonic() - start) * 1000)
                self._log_trace(
                    stage=stage,
                    prompt_id=prompt_id,
                    model=model,
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=latency_ms,
                    status="timeout",
                    error=f"Request timed out after {self._timeout}s",
                )
                raise
            except Exception as e:
                latency_ms = int((time.monotonic() - start) * 1000)
                self._log_trace(
                    stage=stage,
                    prompt_id=prompt_id,
                    model=model,
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=latency_ms,
                    status="error",
                    error=str(e),
                )
                raise

    async def search(
        self,
        *,
        model: str,
        input: str,
        stage: str,
        prompt_id: str | None = None,
        user_location: dict | None = None,
    ):
        """Call Responses API with web_search tool (no structured output)."""
        async with self._semaphore:
            start = time.monotonic()
            try:
                tool: dict = {"type": "web_search"}
                if user_location:
                    tool["user_location"] = user_location
                response = await asyncio.wait_for(
                    self._client.responses.create(
                        model=model,
                        tools=[tool],
                        input=input,
                    ),
                    timeout=self._timeout,
                )
                latency_ms = int((time.monotonic() - start) * 1000)

                tokens_in = response.usage.input_tokens if response.usage else 0
                tokens_out = response.usage.output_tokens if response.usage else 0

                self._log_trace(
                    stage=stage,
                    prompt_id=prompt_id,
                    model=model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=latency_ms,
                    status="success",
                    extra_cost=WEB_SEARCH_COST_PER_CALL,
                )
                return response
            except asyncio.TimeoutError:
                latency_ms = int((time.monotonic() - start) * 1000)
                self._log_trace(
                    stage=stage,
                    prompt_id=prompt_id,
                    model=model,
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=latency_ms,
                    status="timeout",
                    error=f"Request timed out after {self._timeout}s",
                )
                raise
            except Exception as e:
                latency_ms = int((time.monotonic() - start) * 1000)
                self._log_trace(
                    stage=stage,
                    prompt_id=prompt_id,
                    model=model,
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=latency_ms,
                    status="error",
                    error=str(e),
                )
                raise

    def _log_trace(
        self,
        *,
        stage: str,
        prompt_id: str | None,
        model: str,
        tokens_in: int,
        tokens_out: int,
        latency_ms: int,
        status: str,
        error: str | None = None,
        extra_cost: float = 0.0,
    ) -> None:
        if self._trace_path is None:
            return

        cost = _estimate_cost(model, tokens_in, tokens_out) + extra_cost
        entry = TraceEntry(
            timestamp=datetime.now(timezone.utc),
            stage=stage,
            prompt_id=prompt_id,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            cost_usd=round(cost, 6),
            status=status,
            error=error,
        )
        with open(self._trace_path, "a") as f:
            f.write(entry.model_dump_json() + "\n")
