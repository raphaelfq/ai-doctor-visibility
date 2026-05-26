"""Compare Judge V2 (stored in examples/) vs Judge V3 (decomposed) on the same data.

Loads existing report.json, re-runs only the judge stage, and compares verdicts.
No simulator calls — pure judge comparison on identical inputs.

Usage:
    python scripts/compare_judges.py examples/dr_fernando_lopes
    python scripts/compare_judges.py examples/dra_karina_zold
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_visibility.llm import LLMClient
from ai_visibility.models import (
    DoctorInput,
    GeneratedPrompt,
    Report,
    SimulatedResponse,
    Verdict,
)
from ai_visibility.stages.judge import judge_all
from ai_visibility.stages.scorer import score


async def main(data_dir: Path):
    # Load existing report
    report_path = data_dir / "report.json"
    if not report_path.exists():
        print(f"ERROR: {report_path} not found")
        return

    report = Report.model_validate_json(report_path.read_text())
    doctor = report.doctor
    prompts = report.prompts
    responses = report.responses
    old_verdicts = report.verdicts
    old_score = report.score

    print(f"=== Comparing judges for {doctor.name} ===")
    print(f"Using {len(responses)} stored simulator responses (no new API calls for search)")
    print()

    # Run new judge on same data
    trace_path = data_dir / "trace_v3_judge.jsonl"
    if trace_path.exists():
        trace_path.unlink()

    client = LLMClient(trace_path=trace_path)
    new_verdicts = await judge_all(doctor, prompts, responses, client)
    new_score = score(new_verdicts)

    # Flush langfuse
    try:
        from langfuse import get_client
        get_client().flush()
    except Exception:
        pass

    # Compare verdict by verdict
    print(f"{'':4s} | {'V2 (old)':25s} | {'conf':>5s} | {'V3 (new)':25s} | {'conf':>5s} | Match?")
    print("-" * 85)

    matches = 0
    for old_v, new_v in zip(old_verdicts, new_verdicts):
        pid = old_v.prompt_id
        match = "✅" if old_v.citation_type == new_v.citation_type else "❌"
        if old_v.citation_type == new_v.citation_type:
            matches += 1
        print(
            f"{pid:4s} | {old_v.citation_type:25s} | {old_v.confidence:5.2f} "
            f"| {new_v.citation_type:25s} | {new_v.confidence:5.2f} | {match}"
        )

    print()
    print(f"Agreement: {matches}/{len(old_verdicts)} ({100*matches/len(old_verdicts):.0f}%)")
    print()

    # Compare scores
    print(f"{'Dimension':20s} | {'V2':>8s} | {'V3':>8s} | {'Δ':>8s}")
    print("-" * 50)
    for dim in ["presence", "quality", "position", "competitive", "overall"]:
        v2 = getattr(old_score, dim)
        v3 = getattr(new_score, dim)
        delta = v3 - v2
        sign = "+" if delta > 0 else ""
        print(f"{dim:20s} | {v2:8.1f} | {v3:8.1f} | {sign}{delta:7.1f}")

    print()

    # Show V3 reasoning for disagreements
    print("=== DISAGREEMENTS (V3 reasoning) ===")
    print()
    for old_v, new_v in zip(old_verdicts, new_verdicts):
        if old_v.citation_type != new_v.citation_type:
            prompt = next(p for p in prompts if p.id == old_v.prompt_id)
            resp = next(r for r in responses if r.prompt_id == old_v.prompt_id)
            has_name = doctor.name.split()[-1] in resp.raw_text

            print(f"--- {old_v.prompt_id} ({prompt.persona}) ---")
            print(f"  V2: {old_v.citation_type} (conf={old_v.confidence:.2f})")
            print(f"  V3: {new_v.citation_type} (conf={new_v.confidence:.2f})")
            print(f"  Doctor name in text: {has_name}")
            print(f"  V3 evidence: {new_v.evidence_quote[:150]}...")
            print()

    # Cost of re-judge
    total_cost = 0.0
    if trace_path.exists():
        for line in trace_path.read_text().splitlines():
            if line.strip():
                entry = json.loads(line)
                total_cost += entry.get("cost_usd", 0)
    print(f"V3 judge cost: ${total_cost:.4f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/compare_judges.py <path-to-example-dir>")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    asyncio.run(main(data_dir))
