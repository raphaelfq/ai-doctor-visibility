"""Stage 2 — Search Simulator.

Runs each patient prompt against the OpenAI API with web_search,
returning real search results with cited sources.

Design:
- Uses client.responses.create with web_search tool
- Does NOT use structured output (incompatible with web_search)
- Extracts citations from response annotations
- Parallel execution via asyncio.gather
"""

import asyncio
import logging
import time

from ai_visibility.config import settings
from ai_visibility.llm import LLMClient
from ai_visibility.models import Citation, GeneratedPrompt, SimulatedResponse

logger = logging.getLogger(__name__)


async def _simulate_one(
    prompt: GeneratedPrompt,
    client: LLMClient,
    user_location: dict | None = None,
) -> SimulatedResponse:
    """Run a single prompt through the search simulator."""
    response = await client.search(
        model=settings.model_simulator,
        input=prompt.text,
        stage="simulator",
        prompt_id=prompt.id,
        user_location=user_location,
    )

    # Extract text from response
    raw_text = response.output_text or ""

    # Extract citations from annotations
    citations: list[Citation] = []
    for item in response.output:
        if item.type == "message":
            for block in item.content:
                if hasattr(block, "annotations") and block.annotations:
                    for ann in block.annotations:
                        if hasattr(ann, "url") and hasattr(ann, "title"):
                            citations.append(
                                Citation(url=ann.url, title=ann.title or "")
                            )

    # Token usage
    tokens_in = response.usage.input_tokens if response.usage else 0
    tokens_out = response.usage.output_tokens if response.usage else 0

    return SimulatedResponse(
        prompt_id=prompt.id,
        raw_text=raw_text,
        doctors_named=[],  # Extraction delegated to Judge (Stage 3)
        citations=citations,
        model=settings.model_simulator,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=0,  # Tracked in trace.jsonl by LLMClient
    )


async def simulate_searches(
    prompts: list[GeneratedPrompt],
    client: LLMClient,
    user_location: dict | None = None,
) -> list[SimulatedResponse]:
    """Run all prompts through the search simulator in parallel."""
    tasks = [_simulate_one(prompt, client, user_location) for prompt in prompts]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    responses: list[SimulatedResponse] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning("Search simulation failed for prompt %s: %s", prompts[i].id, result)
            # Create a failed response entry
            responses.append(
                SimulatedResponse(
                    prompt_id=prompts[i].id,
                    raw_text=f"[ERRO: {type(result).__name__}: {result}]",
                    model=settings.model_simulator,
                    tokens_in=0,
                    tokens_out=0,
                    latency_ms=0,
                )
            )
        else:
            responses.append(result)

    return responses


if __name__ == "__main__":
    import asyncio
    from pathlib import Path

    from ai_visibility.models import GeneratedPrompt

    async def _test():
        client = LLMClient(trace_path=Path("trace_test.jsonl"))
        prompt = GeneratedPrompt(
            id="p1",
            text="Preciso de dermatologista bom com psoríase em Campinas",
            persona="leigo_ansioso",
            intent_summary="Busca dermatologista para psoríase",
        )
        results = await simulate_searches([prompt], client)
        for r in results:
            print(f"--- {r.prompt_id} ---")
            print(r.raw_text[:500])
            print(f"Citations: {len(r.citations)}")
            for c in r.citations:
                print(f"  - {c.title}: {c.url}")

    asyncio.run(_test())
