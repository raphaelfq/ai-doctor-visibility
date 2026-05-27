"""JSON API routes for the Next.js frontend."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ai_visibility.models import DoctorInput, Report
from ai_visibility.stages.scorer import generate_recommendations, get_benchmark
from ai_visibility.web.background import start_pipeline_run
from ai_visibility.web.db import (
    create_doctor,
    delete_doctor,
    get_doctor,
    get_run,
    list_doctors_with_counts,
    list_recent_runs,
    list_runs_for_doctor,
)

api_router = APIRouter(prefix="/api", tags=["api"])


# ---------- Request / Response schemas ----------


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


@api_router.get("/doctors")
async def api_list_doctors():
    """List all doctors with their run count and latest score."""
    return list_doctors_with_counts()


@api_router.get("/doctors/{doctor_id}")
async def api_get_doctor(doctor_id: str):
    """Get a single doctor with their run history (summary only, no report_json)."""
    doctor = get_doctor(doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    runs = list_runs_for_doctor(doctor_id)
    run_summaries = []
    for r in runs:
        run_summaries.append({
            "id": str(r["id"]),
            "status": r["status"],
            "score": r["score"],
            "progress": r.get("progress", ""),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            "completed_at": r["completed_at"].isoformat() if r.get("completed_at") else None,
        })
    return {
        **{k: (str(v) if k == "id" else v.isoformat() if k == "created_at" else v) for k, v in doctor.items()},
        "runs": run_summaries,
    }


@api_router.post("/doctors", status_code=201)
async def api_create_doctor(body: DoctorCreate):
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
    return {**{k: (str(v) if k == "id" else v.isoformat() if k == "created_at" else v) for k, v in doctor.items()}}


@api_router.delete("/doctors/{doctor_id}", status_code=204)
async def api_delete_doctor(doctor_id: str):
    """Delete a doctor and all their runs (CASCADE)."""
    doctor = get_doctor(doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    delete_doctor(doctor_id)


# ---------- Runs ----------


@api_router.get("/runs")
async def api_list_runs():
    """List recent runs with doctor info."""
    runs = list_recent_runs(limit=20)
    result = []
    for r in runs:
        result.append({
            "id": str(r["id"]),
            "doctor_id": str(r["doctor_id"]),
            "doctor_name": r.get("doctor_name", ""),
            "specialty": r.get("specialty", ""),
            "city": r.get("city", ""),
            "status": r["status"],
            "score": r["score"],
            "progress": r.get("progress", ""),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            "completed_at": r["completed_at"].isoformat() if r.get("completed_at") else None,
        })
    return result


@api_router.get("/runs/{run_id}")
async def api_get_run(run_id: str):
    """Get full run detail including report and recommendations if completed."""
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    result: dict = {
        "id": str(run["id"]),
        "doctor_id": str(run["doctor_id"]),
        "doctor_name": run.get("doctor_name", ""),
        "specialty": run.get("specialty", ""),
        "city": run.get("city", ""),
        "state": run.get("state"),
        "neighborhood": run.get("neighborhood"),
        "crm": run.get("crm"),
        "crm_state": run.get("crm_state"),
        "status": run["status"],
        "score": run["score"],
        "error": run.get("error"),
        "progress": run.get("progress", ""),
        "created_at": run["created_at"].isoformat() if run.get("created_at") else None,
        "completed_at": run["completed_at"].isoformat() if run.get("completed_at") else None,
    }

    if run["status"] == "completed" and run.get("report_json"):
        report_data = run["report_json"]
        if isinstance(report_data, str):
            report = Report.model_validate_json(report_data)
        else:
            report = Report.model_validate(report_data)

        result["report"] = report.model_dump(mode="json")
        result["recommendations"] = generate_recommendations(
            report.verdicts, report.score, report.doctor.name, report.doctor.specialty
        )
        result["benchmark"] = get_benchmark(report.doctor.specialty)

    return result


@api_router.post("/runs", status_code=201)
async def api_create_run(body: RunCreate):
    """Create a run and start the background pipeline."""
    from ai_visibility.web.db import create_run

    doctor_row = get_doctor(body.doctor_id)
    if not doctor_row:
        raise HTTPException(status_code=404, detail="Doctor not found")

    run_id = create_run(doctor_id=body.doctor_id)

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

    return {"run_id": run_id, "status": "pending"}


@api_router.get("/runs/{run_id}/status")
async def api_run_status(run_id: str):
    """Lightweight polling endpoint for run status."""
    run = get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "status": run["status"],
        "progress": run.get("progress", ""),
        "score": run["score"],
    }
