"""Background pipeline runner — executes the AI visibility pipeline in a separate thread."""

from __future__ import annotations

import asyncio
import tempfile
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

from ai_visibility.models import DoctorInput
from ai_visibility.web.db import update_run_status


def start_pipeline_run(run_id: str, doctor: DoctorInput) -> None:
    """Spawn a daemon thread to execute the pipeline for a given run."""
    thread = threading.Thread(
        target=_run_in_thread,
        args=(run_id, doctor),
        daemon=True,
        name=f"pipeline-{run_id[:8]}",
    )
    thread.start()


def _run_in_thread(run_id: str, doctor: DoctorInput) -> None:
    """Thread target: runs the async pipeline in its own event loop."""
    update_run_status(run_id, status="running")

    try:
        output_dir = Path(tempfile.mkdtemp(prefix=f"visibility_{run_id[:8]}_"))

        def on_progress(msg: str) -> None:
            update_run_status(run_id, status="running", progress=msg)

        from ai_visibility.pipeline import run_pipeline

        report = asyncio.run(
            run_pipeline(doctor, output_dir, on_progress=on_progress)
        )

        update_run_status(
            run_id,
            status="completed",
            score=report.score.overall,
            report_json=report.model_dump_json(),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

        # Auto-register top competitor as a doctor
        try:
            from ai_visibility.web.competitor import register_top_competitor

            register_top_competitor(report)
        except Exception:
            pass  # Best-effort — don't fail the run for competitor registration
    except Exception as e:
        update_run_status(
            run_id,
            status="failed",
            error=f"{type(e).__name__}: {e}",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
