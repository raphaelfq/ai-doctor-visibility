"""Route handlers for the web UI."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ai_visibility.web.api_routes import require_api_key

from ai_visibility.models import DoctorInput, Report, Verdict
from ai_visibility.stages.scorer import score as calc_score
from ai_visibility.web.background import start_pipeline_run
from ai_visibility.web.db import (
    create_doctor,
    create_run,
    delete_doctor,
    get_doctor,
    get_pool,
    get_run,
    has_active_run,
    list_doctors,
    list_recent_runs,
    list_runs_for_doctor,
    update_run_status,
)

router = APIRouter()


def _parse_report(report_data: dict | str) -> Report:
    """Parse report_json, migrating old score format if needed."""
    if isinstance(report_data, str):
        report_data = json.loads(report_data)
    score_data = report_data.get("score", {})
    if "visibility" not in score_data and "quality" in score_data:
        parsed_verdicts = [Verdict(**v) for v in report_data.get("verdicts", [])]
        report_data["score"] = calc_score(parsed_verdicts).model_dump()
    report_data.pop("cfm_validation", None)
    return Report.model_validate(report_data)


def _render(request: Request, name: str, context: dict | None = None):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, name, context or {})


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    doctors = list_doctors()
    runs = list_recent_runs()
    return _render(request, "dashboard.html", {"doctors": doctors, "runs": runs})


# ---------------------------------------------------------------------------
# Doctors
# ---------------------------------------------------------------------------


@router.get("/doctors", response_class=HTMLResponse)
def doctors_list(request: Request):
    doctors = list_doctors()
    return _render(request, "doctors/list.html", {"doctors": doctors})


@router.get("/doctors/new", response_class=HTMLResponse)
def doctor_new_form(request: Request):
    return _render(request, "doctors/new.html")


@router.post("/doctors")
def doctor_create(
    request: Request,
    name: str = Form(...),
    specialty: str = Form(...),
    city: str = Form(...),
    state: str = Form(""),
    neighborhood: str = Form(""),
    crm: str = Form(""),
    crm_state: str = Form(""),
):
    doctor_id = create_doctor(
        name=name,
        specialty=specialty,
        city=city,
        state=state or None,
        neighborhood=neighborhood or None,
        crm=crm or None,
        crm_state=crm_state or None,
    )
    return RedirectResponse(url=f"/doctors/{doctor_id}", status_code=303)


@router.get("/doctors/{doctor_id}", response_class=HTMLResponse)
def doctor_detail(request: Request, doctor_id: str):
    doctor = get_doctor(doctor_id)
    if not doctor:
        return HTMLResponse("Medico nao encontrado", status_code=404)
    runs = list_runs_for_doctor(doctor_id)
    return _render(request, "doctors/detail.html", {"doctor": doctor, "runs": runs})


@router.post("/doctors/{doctor_id}/delete")
def doctor_delete(doctor_id: str):
    delete_doctor(doctor_id)
    return RedirectResponse(url="/doctors", status_code=303)


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


@router.get("/runs/new", response_class=HTMLResponse)
def run_new_form(request: Request, doctor_id: str | None = None):
    doctor = get_doctor(doctor_id) if doctor_id else None
    doctors = list_doctors() if not doctor else []
    return _render(request, "runs/new.html", {"doctor": doctor, "doctors": doctors})


@router.post("/runs")
def run_create(
    request: Request,
    doctor_id: str = Form(...),
):
    doctor_row = get_doctor(doctor_id)
    if not doctor_row:
        return HTMLResponse("Medico nao encontrado", status_code=404)

    if has_active_run(doctor_id):
        return HTMLResponse("Este medico ja possui uma analise em andamento", status_code=409)

    run_id = create_run(doctor_id=doctor_id)

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

    return RedirectResponse(url=f"/runs/{run_id}", status_code=303)


@router.get("/runs/{run_id}", response_class=HTMLResponse)
def run_detail(request: Request, run_id: str):
    run = get_run(run_id)
    if not run:
        return HTMLResponse("Analise nao encontrada", status_code=404)

    report = None
    if run["status"] == "completed" and run.get("report_json"):
        report = _parse_report(run["report_json"])

    return _render(request, "runs/detail.html", {"run": run, "report": report})


@router.get("/runs/{run_id}/status", response_class=HTMLResponse)
def run_status_partial(request: Request, run_id: str):
    run = get_run(run_id)
    if not run:
        return HTMLResponse("Analise nao encontrada", status_code=404)

    report = None
    if run["status"] == "completed" and run.get("report_json"):
        report = _parse_report(run["report_json"])

    return _render(request, "_partials/run_status.html", {"run": run, "report": report})


# ---------------------------------------------------------------------------
# Seed API (import example data)
# ---------------------------------------------------------------------------


@router.post("/api/seed", dependencies=[Depends(require_api_key)])
async def seed_data(request: Request):
    """Import a report JSON payload as a completed run. Used to seed prod with examples."""
    body = await request.json()
    report_data = body.get("report")
    if not report_data:
        return JSONResponse({"error": "missing report"}, status_code=400)

    # Validate the report payload matches our model
    try:
        report = _parse_report(report_data)
    except Exception as e:
        return JSONResponse({"error": f"Invalid report: {e}"}, status_code=422)

    d = report_data["doctor"]
    name = d["name"]

    # Find or create doctor
    with get_pool().connection() as conn:
        row = conn.execute("SELECT id FROM doctors WHERE name = %s", (name,)).fetchone()

    if row:
        doctor_id = str(row["id"])
    else:
        doctor_id = create_doctor(
            name=name, specialty=d["specialty"], city=d["city"],
            state=d.get("state"), neighborhood=d.get("neighborhood"),
            crm=d.get("crm"), crm_state=d.get("crm_state"),
        )

    # Create run
    run_id = str(uuid.uuid4())
    generated_at = report_data["metadata"]["generated_at"]
    with get_pool().connection() as conn:
        conn.execute(
            """INSERT INTO runs (id, doctor_id, status, score, report_json, created_at, completed_at)
               VALUES (%s, %s, 'completed', %s, %s::jsonb, %s, %s)""",
            (run_id, doctor_id, report_data["score"]["overall"],
             json.dumps(report_data), generated_at, generated_at),
        )

    return JSONResponse({"doctor_id": doctor_id, "run_id": run_id, "score": report_data["score"]["overall"]})
