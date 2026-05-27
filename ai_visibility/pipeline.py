"""Pipeline orchestrator — runs CFM validation + 4 stages + reporters."""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from ai_visibility.config import settings
from ai_visibility.llm import LLMClient
from ai_visibility.models import (
    DoctorInput,
    GeneratedPrompt,
    Report,
    ReportMetadata,
    TraceEntry,
)
from ai_visibility.stages.judge import judge_all
from ai_visibility.stages.prompts import generate_prompts
from ai_visibility.stages.scorer import score
from ai_visibility.stages.simulator import simulate_searches

logger = logging.getLogger(__name__)


async def run_pipeline(
    doctor: DoctorInput,
    output_dir: Path,
    on_progress: Callable[[str], None] | None = None,
) -> Report:
    """Execute the full diagnostic pipeline and return a Report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_path = output_dir / "trace.jsonl"

    # Clear previous trace
    if trace_path.exists():
        trace_path.unlink()

    client = LLMClient(trace_path=trace_path)
    start_time = time.monotonic()

    def _progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    # --- Stage 1: Prompt Generator ---
    _progress("Gerando prompts de paciente...")

    raw_prompts = await generate_prompts(doctor, client)

    # Handle cached prompts (returned as list[dict] from cache)
    prompts: list[GeneratedPrompt] = []
    for p in raw_prompts:
        if isinstance(p, dict):
            prompts.append(GeneratedPrompt(**p))
        else:
            prompts.append(p)

    _progress(f"✓ {len(prompts)} prompts gerados")

    # --- Stage 2: Search Simulator ---
    _progress("Simulando buscas com web_search...")
    user_location = {
        "type": "approximate",
        "city": doctor.city,
        "region": doctor.state or "",
        "country": "BR",
    }
    responses = await simulate_searches(prompts, client, user_location)
    _progress(f"✓ {len(responses)} buscas concluídas")

    # --- Stage 3: Judge ---
    _progress("Avaliando respostas com LLM-as-Judge...")
    verdicts = await judge_all(doctor, prompts, responses, client)
    _progress(f"✓ {len(verdicts)} avaliações concluídas")

    # --- Stage 4: Scorer ---
    _progress("Calculando AI Visibility Score...")
    score_result = score(verdicts)

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    # --- Aggregate metadata from trace ---
    total_tokens_in = 0
    total_tokens_out = 0
    total_cost = 0.0
    if trace_path.exists():
        for line in trace_path.read_text().splitlines():
            if line.strip():
                entry = json.loads(line)
                total_tokens_in += entry.get("tokens_in", 0)
                total_tokens_out += entry.get("tokens_out", 0)
                total_cost += entry.get("cost_usd", 0.0)

    metadata = ReportMetadata(
        generated_at=datetime.now(timezone.utc),
        model_generator=settings.model_generator,
        model_simulator=settings.model_simulator,
        model_judge=settings.model_judge,
        total_tokens_in=total_tokens_in,
        total_tokens_out=total_tokens_out,
        total_cost_usd=round(total_cost, 4),
        seed=settings.seed,
    )

    report = Report(
        doctor=doctor,
        prompts=prompts,
        responses=responses,
        verdicts=verdicts,
        score=score_result,
        metadata=metadata,
    )

    _progress(
        f"✓ Score: {score_result.overall:.0f}/100 "
        f"({elapsed_ms / 1000:.1f}s, ${total_cost:.4f})"
    )

    # Flush Langfuse traces before returning (ensures all data is sent)
    try:
        from langfuse import get_client

        langfuse = get_client()
        langfuse.flush()
    except (ImportError, RuntimeError):
        pass  # Langfuse is optional — don't break pipeline if not configured

    logger.info(
        "Pipeline completed for %s: score=%.1f, cost=$%.4f, elapsed=%.1fs",
        doctor.name, score_result.overall, total_cost, elapsed_ms / 1000,
    )

    return report
