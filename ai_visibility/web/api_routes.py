"""JSON API routes for the Next.js frontend."""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from ai_visibility.models import DoctorInput, Report, Verdict
from ai_visibility.stages.scorer import generate_recommendations, get_benchmark
from ai_visibility.web.background import start_pipeline_run
from ai_visibility.web.db import (
    create_doctor,
    delete_doctor,
    get_doctor,
    get_run,
    has_active_run,
    list_doctors_with_counts,
    list_recent_runs,
    list_runs_for_doctor,
)

logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api", tags=["api"])

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: str | None = Depends(_api_key_header)):
    """Validate API key for mutating endpoints. Auth disabled when admin_api_key is empty."""
    from ai_visibility.config import settings

    if not settings.admin_api_key:
        return  # Auth disabled (dev mode)
    if api_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------- Response models ----------


class DoctorSummary(BaseModel):
    id: str
    name: str
    specialty: str
    city: str
    state: str | None = None
    neighborhood: str | None = None
    crm: str | None = None
    crm_state: str | None = None
    created_at: datetime | None = None
    run_count: int = 0
    latest_score: float | None = None


class RunSummary(BaseModel):
    id: str
    doctor_id: str
    doctor_name: str = ""
    specialty: str = ""
    city: str = ""
    status: str
    score: float | None = None
    progress: str = ""
    created_at: datetime | None = None
    completed_at: datetime | None = None


class DoctorDetail(DoctorSummary):
    runs: list[RunSummary] = []


class RunDetail(RunSummary):
    state: str | None = None
    neighborhood: str | None = None
    crm: str | None = None
    crm_state: str | None = None
    error: str | None = None
    report: dict | None = None
    recommendations: list[str] | None = None
    benchmark: float | None = None


class RunStatusResponse(BaseModel):
    status: str
    progress: str = ""
    score: float | None = None


class RunCreateResponse(BaseModel):
    run_id: str
    status: str


# ---------- Request schemas ----------


class DoctorCreate(BaseModel):
    name: str
    specialty: str
    city: str
    state: str | None = None
    neighborhood: str | None = None
    crm: str | None = None
    crm_state: str | None = None


class RunCreate(BaseModel):
    doctor_id: str


# ---------- Doctors ----------


@api_router.get("/doctors", response_model=list[DoctorSummary])
def api_list_doctors():
    """List all doctors with their run count and latest score."""
    rows = list_doctors_with_counts()
    return [DoctorSummary(**row) for row in rows]


@api_router.get("/doctors/{doctor_id}", response_model=DoctorDetail)
def api_get_doctor(doctor_id: UUID):
    """Get a single doctor with their run history (summary only, no report_json)."""
    doctor = get_doctor(str(doctor_id))
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    runs = list_runs_for_doctor(str(doctor_id))
    run_summaries = [
        RunSummary(
            id=str(r["id"]),
            doctor_id=str(r.get("doctor_id", doctor_id)),
            status=r["status"],
            score=r.get("score"),
            progress=r.get("progress", ""),
            created_at=r.get("created_at"),
            completed_at=r.get("completed_at"),
        )
        for r in runs
    ]
    return DoctorDetail(
        id=str(doctor["id"]),
        name=doctor["name"],
        specialty=doctor["specialty"],
        city=doctor["city"],
        state=doctor.get("state"),
        neighborhood=doctor.get("neighborhood"),
        crm=doctor.get("crm"),
        crm_state=doctor.get("crm_state"),
        created_at=doctor.get("created_at"),
        runs=run_summaries,
    )


@api_router.post("/doctors", status_code=201, response_model=DoctorSummary, dependencies=[Depends(require_api_key)])
def api_create_doctor(body: DoctorCreate):
    """Create a new doctor."""
    doctor_id = create_doctor(
        name=body.name,
        specialty=body.specialty,
        city=body.city,
        state=body.state,
        neighborhood=body.neighborhood,
        crm=body.crm,
        crm_state=body.crm_state,
    )
    doctor = get_doctor(doctor_id)
    return DoctorSummary(
        id=str(doctor["id"]),
        name=doctor["name"],
        specialty=doctor["specialty"],
        city=doctor["city"],
        state=doctor.get("state"),
        neighborhood=doctor.get("neighborhood"),
        crm=doctor.get("crm"),
        crm_state=doctor.get("crm_state"),
        created_at=doctor.get("created_at"),
    )


@api_router.delete("/doctors/{doctor_id}", status_code=204, dependencies=[Depends(require_api_key)])
def api_delete_doctor(doctor_id: UUID):
    """Delete a doctor and all their runs (CASCADE)."""
    doctor = get_doctor(str(doctor_id))
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    delete_doctor(str(doctor_id))


# ---------- Runs ----------


@api_router.get("/runs", response_model=list[RunSummary])
def api_list_runs():
    """List recent runs with doctor info."""
    runs = list_recent_runs(limit=20)
    return [
        RunSummary(
            id=str(r["id"]),
            doctor_id=str(r["doctor_id"]),
            doctor_name=r.get("doctor_name", ""),
            specialty=r.get("specialty", ""),
            city=r.get("city", ""),
            status=r["status"],
            score=r.get("score"),
            progress=r.get("progress", ""),
            created_at=r.get("created_at"),
            completed_at=r.get("completed_at"),
        )
        for r in runs
    ]


@api_router.get("/runs/{run_id}", response_model=RunDetail)
def api_get_run(run_id: UUID):
    """Get full run detail including report and recommendations if completed."""
    run = get_run(str(run_id))
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    detail = RunDetail(
        id=str(run["id"]),
        doctor_id=str(run["doctor_id"]),
        doctor_name=run.get("doctor_name", ""),
        specialty=run.get("specialty", ""),
        city=run.get("city", ""),
        state=run.get("state"),
        neighborhood=run.get("neighborhood"),
        crm=run.get("crm"),
        crm_state=run.get("crm_state"),
        status=run["status"],
        score=run.get("score"),
        error=run.get("error"),
        progress=run.get("progress", ""),
        created_at=run.get("created_at"),
        completed_at=run.get("completed_at"),
    )

    if run["status"] == "completed" and run.get("report_json"):
        report_data = run["report_json"]
        if isinstance(report_data, str):
            import json as _json
            report_data = _json.loads(report_data)

        # Migrate old score format (presence/quality/position/competitive)
        # to new format (visibility/dominance/indirect_presence)
        score_data = report_data.get("score", {})
        if "visibility" not in score_data and "quality" in score_data:
            from ai_visibility.stages.scorer import score as calc_score
            verdicts_raw = report_data.get("verdicts", [])
            parsed_verdicts = [Verdict(**v) for v in verdicts_raw]
            new_score = calc_score(parsed_verdicts)
            report_data["score"] = new_score.model_dump()

        report = Report.model_validate(report_data)

        detail.report = report.model_dump(mode="json")
        detail.recommendations = generate_recommendations(
            report.verdicts, report.score, report.doctor.name, report.doctor.specialty
        )
        detail.benchmark = get_benchmark(report.doctor.specialty)

    return detail


@api_router.post("/runs", status_code=201, response_model=RunCreateResponse, dependencies=[Depends(require_api_key)])
def api_create_run(body: RunCreate):
    """Create a run and start the background pipeline."""
    from ai_visibility.web.db import create_run

    doctor_row = get_doctor(body.doctor_id)
    if not doctor_row:
        raise HTTPException(status_code=404, detail="Doctor not found")

    if has_active_run(body.doctor_id):
        raise HTTPException(status_code=409, detail="Doctor already has a pending or running analysis")

    run_id = create_run(doctor_id=body.doctor_id)

    logger.info("Created run %s for doctor %s", run_id, doctor_row["name"])

    doctor_input = DoctorInput(
        name=doctor_row["name"],
        specialty=doctor_row["specialty"],
        city=doctor_row["city"],
        state=doctor_row.get("state"),
        neighborhood=doctor_row.get("neighborhood"),
        crm=doctor_row.get("crm"),
        crm_state=doctor_row.get("crm_state"),
    )
    start_pipeline_run(run_id, doctor_input)

    return RunCreateResponse(run_id=run_id, status="pending")


@api_router.get("/runs/{run_id}/status", response_model=RunStatusResponse)
def api_run_status(run_id: UUID):
    """Lightweight polling endpoint for run status."""
    run = get_run(str(run_id))
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunStatusResponse(
        status=run["status"],
        progress=run.get("progress", ""),
        score=run.get("score"),
    )
