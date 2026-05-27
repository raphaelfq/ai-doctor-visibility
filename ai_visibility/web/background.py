"""Background pipeline runner — executes the AI visibility pipeline in a separate thread."""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from ai_visibility.models import DoctorInput
from ai_visibility.web.db import update_run_status

logger = logging.getLogger(__name__)


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
    logger.info("Starting pipeline run %s for %s", run_id, doctor.name)
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

        shutil.rmtree(output_dir, ignore_errors=True)
    except Exception as e:
        logger.exception("Pipeline failed for run %s", run_id)
        update_run_status(
            run_id,
            status="failed",
            error=f"{type(e).__name__}: {e}",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
