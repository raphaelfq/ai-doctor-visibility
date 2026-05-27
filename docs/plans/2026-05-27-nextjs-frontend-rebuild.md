# Next.js Frontend Rebuild Implementation Plan

> **For Agents:** REQUIRED SUB-SKILL: Use ring:executing-plans to implement this plan task-by-task.

**Goal:** Replace the Jinja2/DaisyUI frontend with a Next.js + shadcn/ui + Recharts SPA that communicates with the existing FastAPI backend via JSON API, producing a Semrush-quality UI for the iMedicina AI Visibility POC.

**Architecture:** The FastAPI backend gains a new `/api` router returning JSON. A separate Next.js app (in `frontend/`) consumes this API. Both services run in Docker Compose. The frontend uses SWR for data fetching/polling and shadcn/ui for all UI components.

**Tech Stack:** Next.js 14 (App Router, TypeScript, Tailwind CSS 3), shadcn/ui, Recharts, SWR, Lucide React, Docker multi-stage Node 20 build.

**Global Prerequisites:**
- Environment: macOS or Linux, Node.js 20+, npm 10+, Python 3.11+, Docker
- Tools: `node --version`, `npm --version`, `docker --version`
- Access: FastAPI backend running on port 8000 (or via Docker Compose)
- State: Branch `feat/nextjs-frontend` from `feat/ui-redesign-daisyui`

**Verification before starting:**
```bash
node --version        # Expected: v20.x or v22.x
npm --version         # Expected: 10.x+
docker --version      # Expected: Docker 24+
python3 --version     # Expected: Python 3.11+
git status            # Expected: clean working tree
```

---

## Phase 1: Backend JSON API (Tasks 1-6)

### Task 1: Create the API router file with doctor endpoints

**Files:**
- Create: `ai_visibility/web/api_routes.py`

**Prerequisites:**
- Python 3.11+, FastAPI installed

**Step 1: Create the API router file**

Create `ai_visibility/web/api_routes.py` with the following complete content:

```python
"""JSON API routes for the Next.js frontend."""

from __future__ import annotations

import json

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
    # Strip report_json from run summaries to keep response lightweight
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
```

**Step 2: Verify file was created**

Run: `python3 -c "import ast; ast.parse(open('ai_visibility/web/api_routes.py').read()); print('SYNTAX OK')"`

**Expected output:**
```
SYNTAX OK
```

**Step 3: Commit**

```bash
git add ai_visibility/web/api_routes.py
git commit -m "feat(api): add JSON API router for Next.js frontend"
```

**If Task Fails:**
1. **Syntax error:** Check for missing imports or typos in the file
2. **Import error at runtime:** Ensure `list_doctors_with_counts` is added in Task 2
3. **Rollback:** `git checkout -- ai_visibility/web/api_routes.py`

---

### Task 2: Add list_doctors_with_counts to db.py

**Files:**
- Modify: `ai_visibility/web/db.py` (add new function after `delete_doctor`, around line 127)

**Prerequisites:**
- File `ai_visibility/web/db.py` must exist

**Step 1: Add the new function**

Add the following function after the `delete_doctor` function (after line 127) in `ai_visibility/web/db.py`:

```python
def list_doctors_with_counts(limit: int = 100) -> list[dict[str, Any]]:
    """List doctors with run_count and latest_score from their most recent completed run."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT d.*,
                   COUNT(r.id) AS run_count,
                   (SELECT r2.score FROM runs r2
                    WHERE r2.doctor_id = d.id AND r2.status = 'completed'
                    ORDER BY r2.created_at DESC LIMIT 1) AS latest_score
            FROM doctors d
            LEFT JOIN runs r ON r.doctor_id = d.id
            GROUP BY d.id
            ORDER BY d.created_at DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    result = []
    for r in rows:
        row_dict = dict(r)
        row_dict["id"] = str(row_dict["id"])
        if row_dict.get("created_at"):
            row_dict["created_at"] = row_dict["created_at"].isoformat()
        result.append(row_dict)
    return result
```

**Step 2: Verify the function is importable**

Run: `cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility && python3 -c "from ai_visibility.web.db import list_doctors_with_counts; print('IMPORT OK')"`

**Expected output:**
```
IMPORT OK
```

**Step 3: Commit**

```bash
git add ai_visibility/web/db.py
git commit -m "feat(db): add list_doctors_with_counts with LEFT JOIN for run stats"
```

**If Task Fails:**
1. **SQL syntax error:** Check the subquery parentheses and JOIN syntax
2. **Import error:** Ensure function is at module level, not nested
3. **Rollback:** `git checkout -- ai_visibility/web/db.py`

---

### Task 3: Register API router and add CORS in app.py

**Files:**
- Modify: `ai_visibility/web/app.py` (lines 1-86)

**Prerequisites:**
- `ai_visibility/web/api_routes.py` exists (Task 1)

**Step 1: Add CORS import and middleware**

In `ai_visibility/web/app.py`, add the CORS import near the top imports:

```python
from fastapi.middleware.cors import CORSMiddleware
```

**Step 2: Register the API router and add CORS in create_app()**

In the `create_app()` function, after `app = FastAPI(...)` (line 72), add CORS middleware. After the existing `app.include_router(router)` line (line 84), add the API router:

The `create_app()` function should become:

```python
def create_app() -> FastAPI:
    app = FastAPI(title="AI Visibility", lifespan=lifespan)

    # CORS for Next.js frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://frontend:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["score_color"] = _score_color
    templates.env.filters["score_label"] = _score_label
    templates.env.filters["get_benchmark"] = get_benchmark
    templates.env.filters["render_md"] = _render_md
    templates.env.filters["highlight"] = _highlight
    app.state.templates = templates

    from ai_visibility.web.routes import router

    app.include_router(router)

    from ai_visibility.web.api_routes import api_router

    app.include_router(api_router)

    return app
```

**Step 3: Verify import works**

Run: `cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility && python3 -c "from ai_visibility.web.app import create_app; print('APP OK')"`

**Expected output:**
```
APP OK
```

**Step 4: Commit**

```bash
git add ai_visibility/web/app.py
git commit -m "feat(app): register JSON API router and add CORS for frontend"
```

**If Task Fails:**
1. **Import error on CORSMiddleware:** Ensure `from fastapi.middleware.cors import CORSMiddleware`
2. **Circular import:** The import inside the function body prevents this
3. **Rollback:** `git checkout -- ai_visibility/web/app.py`

---

### Task 4: Verify API endpoints work end-to-end

**Prerequisites:**
- Docker Compose running (`docker compose up -d db app`)
- Tasks 1-3 completed

**Step 1: Start the services**

Run: `cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility && docker compose up -d --build`

**Step 2: Test the doctor list endpoint**

Run: `curl -s http://localhost:8000/api/doctors | python3 -m json.tool | head -20`

**Expected output:** A JSON array (possibly empty if no seeded data):
```json
[]
```

Or if seeded data exists, a list of doctor objects with `run_count` and `latest_score`.

**Step 3: Test doctor creation**

Run: `curl -s -X POST http://localhost:8000/api/doctors -H "Content-Type: application/json" -d '{"name":"Dr. Teste","specialty":"Dermatologia","city":"Campinas"}' | python3 -m json.tool`

**Expected output:**
```json
{
    "id": "<uuid>",
    "name": "Dr. Teste",
    "specialty": "Dermatologia",
    "city": "Campinas",
    ...
}
```

**Step 4: Test runs list**

Run: `curl -s http://localhost:8000/api/runs | python3 -m json.tool`

**Expected output:** A JSON array of run objects.

**Step 5: Test CORS headers**

Run: `curl -s -I -X OPTIONS http://localhost:8000/api/doctors -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: GET" 2>&1 | grep -i access-control`

**Expected output:**
```
access-control-allow-origin: http://localhost:3000
access-control-allow-methods: *
```

**If Task Fails:**
1. **Connection refused:** Ensure Docker containers are running with `docker compose ps`
2. **404 on /api/doctors:** Check that `api_router` is registered in `app.py`
3. **500 error:** Check container logs with `docker compose logs app`
4. **Rollback:** `docker compose down && docker compose up -d --build`

---

### Task 5: Code Review Checkpoint - Backend API

1. **Dispatch all 3 reviewers in parallel:**
   - REQUIRED SUB-SKILL: Use ring:requesting-code-review
   - All reviewers run simultaneously (ring:code-reviewer, ring:business-logic-reviewer, ring:security-reviewer)
   - Wait for all to complete

2. **Handle findings by severity (MANDATORY):**

**Critical/High/Medium Issues:**
- Fix immediately (do NOT add TODO comments for these severities)
- Re-run all 3 reviewers in parallel after fixes
- Repeat until zero Critical/High/Medium issues remain

**Low Issues:**
- Add `TODO(review):` comments in code at the relevant location
- Format: `TODO(review): [Issue description] (reported by [reviewer] on [date], severity: Low)`

**Cosmetic/Nitpick Issues:**
- Add `FIXME(nitpick):` comments in code at the relevant location
- Format: `FIXME(nitpick): [Issue description] (reported by [reviewer] on [date], severity: Cosmetic)`

3. **Proceed only when:**
   - Zero Critical/High/Medium issues remain
   - All Low issues have TODO(review): comments added
   - All Cosmetic issues have FIXME(nitpick): comments added

---

## Phase 2: Next.js Project Setup (Tasks 6-12)

### Task 6: Scaffold Next.js project

**Files:**
- Create: `frontend/` directory with Next.js scaffold

**Prerequisites:**
- Node.js 20+, npm 10+

**Step 1: Create the Next.js project**

Run:
```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --no-turbopack --use-npm
```

When prompted, accept all defaults (Yes to TypeScript, ESLint, Tailwind, src/ directory, App Router; No to Turbopack).

**Step 2: Verify the project was created**

Run: `ls frontend/src/app/layout.tsx frontend/package.json frontend/tsconfig.json`

**Expected output:**
```
frontend/src/app/layout.tsx
frontend/package.json
frontend/tsconfig.json
```

**Step 3: Verify it builds**

Run: `cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility/frontend && npm run build 2>&1 | tail -5`

**Expected output (last lines):**
```
Route (app)                              Size     First Load JS
...
+ First Load JS shared by all            XX kB
```

**Step 4: Commit**

```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
git add frontend/
git commit -m "feat(frontend): scaffold Next.js 14 project with TypeScript and Tailwind"
```

**If Task Fails:**
1. **npx not found:** Install Node.js 20+ via `nvm install 20`
2. **Build fails:** Run `cd frontend && npm install` first
3. **Rollback:** `rm -rf frontend/`

---

### Task 7: Install dependencies (shadcn/ui, SWR, Recharts, Lucide)

**Files:**
- Modify: `frontend/package.json`

**Prerequisites:**
- Task 6 completed (frontend/ exists)

**Step 1: Install runtime dependencies**

Run:
```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility/frontend && npm install swr recharts lucide-react class-variance-authority clsx tailwind-merge
```

**Step 2: Initialize shadcn/ui**

Run:
```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility/frontend && npx shadcn@latest init -d
```

Accept defaults. This creates `components.json` and `src/lib/utils.ts`.

**Step 3: Install shadcn components**

Run:
```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility/frontend && npx shadcn@latest add button card badge input label select separator sheet table tabs dialog -y
```

**Step 4: Verify installation**

Run: `ls frontend/src/components/ui/button.tsx frontend/src/components/ui/card.tsx frontend/src/components/ui/tabs.tsx`

**Expected output:**
```
frontend/src/components/ui/button.tsx
frontend/src/components/ui/card.tsx
frontend/src/components/ui/tabs.tsx
```

**Step 5: Commit**

```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
git add frontend/
git commit -m "feat(frontend): install shadcn/ui, SWR, Recharts, Lucide icons"
```

**If Task Fails:**
1. **shadcn init fails:** Ensure `tailwind.config.ts` exists; run `npx shadcn@latest init` manually
2. **Component not found:** Run individual adds: `npx shadcn@latest add button`
3. **Rollback:** `cd frontend && rm -rf node_modules && npm install`

---

### Task 8: Create API client and TypeScript types

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/types.ts`

**Prerequisites:**
- Task 7 completed

**Step 1: Create TypeScript types**

Create `frontend/src/lib/types.ts`:

```typescript
// Types matching the FastAPI backend Pydantic models

export type CitationType =
  | "mentioned_by_name"
  | "mentioned_as_specialty"
  | "competitor_in_place"
  | "not_mentioned";

export type RunStatus = "pending" | "running" | "completed" | "failed";

export interface Doctor {
  id: string;
  name: string;
  specialty: string;
  city: string;
  state: string | null;
  neighborhood: string | null;
  crm: string | null;
  crm_state: string | null;
  created_at: string;
  run_count?: number;
  latest_score?: number | null;
}

export interface DoctorWithRuns extends Doctor {
  runs: RunSummary[];
}

export interface RunSummary {
  id: string;
  status: RunStatus;
  score: number | null;
  progress: string;
  created_at: string | null;
  completed_at: string | null;
}

export interface RunListItem extends RunSummary {
  doctor_id: string;
  doctor_name: string;
  specialty: string;
  city: string;
}

export interface Citation {
  url: string;
  title: string;
}

export interface GeneratedPrompt {
  id: string;
  text: string;
  persona: string;
  intent_summary: string;
}

export interface SimulatedResponse {
  prompt_id: string;
  raw_text: string;
  doctors_named: string[];
  citations: Citation[];
  model: string;
  tokens_in: number;
  tokens_out: number;
  latency_ms: number;
}

export interface Verdict {
  prompt_id: string;
  citation_type: CitationType;
  confidence: number;
  position: number | null;
  evidence_quote: string;
  competitors_named: string[];
}

export interface ScoreBreakdown {
  presence: number;
  quality: number;
  position: number;
  competitive: number;
  overall: number;
}

export interface CFMValidation {
  valid: boolean | null;
  registered_name: string | null;
  status: string | null;
  specialties: string[];
  rqe_numbers: string[];
  error: string | null;
}

export interface ReportMetadata {
  generated_at: string;
  model_generator: string;
  model_simulator: string;
  model_judge: string;
  total_tokens_in: number;
  total_tokens_out: number;
  total_cost_usd: number;
  seed: number;
}

export interface DoctorInput {
  name: string;
  specialty: string;
  city: string;
  state: string | null;
  neighborhood: string | null;
  crm: string | null;
  crm_state: string | null;
}

export interface Report {
  doctor: DoctorInput;
  cfm_validation: CFMValidation | null;
  prompts: GeneratedPrompt[];
  responses: SimulatedResponse[];
  verdicts: Verdict[];
  score: ScoreBreakdown;
  metadata: ReportMetadata;
}

export interface RunDetail {
  id: string;
  doctor_id: string;
  doctor_name: string;
  specialty: string;
  city: string;
  state: string | null;
  neighborhood: string | null;
  crm: string | null;
  crm_state: string | null;
  status: RunStatus;
  score: number | null;
  error: string | null;
  progress: string;
  created_at: string | null;
  completed_at: string | null;
  report?: Report;
  recommendations?: string[];
  benchmark?: number;
}

export interface RunStatusResponse {
  status: RunStatus;
  progress: string;
  score: number | null;
}

// Helper constants (mirrors backend scorer.py)
export const SCORE_LABELS: Record<string, { max: number; label: string }[]> = {
  default: [
    { max: 20, label: "Invisivel" },
    { max: 40, label: "Baixa" },
    { max: 60, label: "Moderada" },
    { max: 80, label: "Boa" },
    { max: 100, label: "Excelente" },
  ],
};

export function getScoreLabel(score: number): string {
  if (score <= 20) return "Invisivel";
  if (score <= 40) return "Baixa";
  if (score <= 60) return "Moderada";
  if (score <= 80) return "Boa";
  return "Excelente";
}

export function getScoreColor(score: number): string {
  if (score <= 30) return "#ef4444"; // red
  if (score <= 60) return "#f59e0b"; // amber
  return "#22c55e"; // green
}

export const CITATION_TYPE_CONFIG: Record<
  CitationType,
  { label: string; color: string; bg: string; icon: string }
> = {
  mentioned_by_name: {
    label: "Citado por nome",
    color: "text-green-700",
    bg: "bg-green-50 border-green-200",
    icon: "check-circle",
  },
  mentioned_as_specialty: {
    label: "Citado como especialista",
    color: "text-yellow-700",
    bg: "bg-yellow-50 border-yellow-200",
    icon: "circle-dot",
  },
  competitor_in_place: {
    label: "Concorrente citado",
    color: "text-red-700",
    bg: "bg-red-50 border-red-200",
    icon: "x-circle",
  },
  not_mentioned: {
    label: "Nao mencionado",
    color: "text-gray-500",
    bg: "bg-gray-50 border-gray-200",
    icon: "minus-circle",
  },
};
```

**Step 2: Create the API client**

Create `frontend/src/lib/api.ts`:

```typescript
import useSWR, { SWRConfiguration } from "swr";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetcher<T>(url: string): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`);
  if (!res.ok) {
    const error = new Error(`API error: ${res.status}`);
    throw error;
  }
  return res.json();
}

async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const error = new Error(`API error: ${res.status}`);
    throw error;
  }
  return res.json();
}

async function apiDelete(url: string): Promise<void> {
  const res = await fetch(`${API_BASE}${url}`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
}

// ---------- Hooks ----------

import type {
  Doctor,
  DoctorWithRuns,
  RunListItem,
  RunDetail,
  RunStatusResponse,
} from "./types";

export function useDoctors(config?: SWRConfiguration) {
  return useSWR<Doctor[]>("/api/doctors", fetcher, config);
}

export function useDoctor(id: string | null, config?: SWRConfiguration) {
  return useSWR<DoctorWithRuns>(id ? `/api/doctors/${id}` : null, fetcher, config);
}

export function useRuns(config?: SWRConfiguration) {
  return useSWR<RunListItem[]>("/api/runs", fetcher, config);
}

export function useRun(id: string | null, config?: SWRConfiguration) {
  return useSWR<RunDetail>(id ? `/api/runs/${id}` : null, fetcher, config);
}

export function useRunStatus(
  id: string | null,
  shouldPoll: boolean,
  config?: SWRConfiguration
) {
  return useSWR<RunStatusResponse>(
    id && shouldPoll ? `/api/runs/${id}/status` : null,
    fetcher,
    {
      refreshInterval: shouldPoll ? 3000 : 0,
      ...config,
    }
  );
}

// ---------- Mutations ----------

export async function createDoctor(data: {
  name: string;
  specialty: string;
  city: string;
  state?: string;
  neighborhood?: string;
  crm?: string;
  crm_state?: string;
}) {
  return apiPost<Doctor>("/api/doctors", data);
}

export async function deleteDoctor(id: string) {
  return apiDelete(`/api/doctors/${id}`);
}

export async function createRun(doctorId: string) {
  return apiPost<{ run_id: string; status: string }>("/api/runs", {
    doctor_id: doctorId,
  });
}
```

**Step 3: Verify TypeScript compiles**

Run: `cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility/frontend && npx tsc --noEmit 2>&1 | tail -5`

**Expected output:**
```
(no errors, or only warnings from generated shadcn files)
```

**Step 4: Commit**

```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
git add frontend/src/lib/types.ts frontend/src/lib/api.ts
git commit -m "feat(frontend): add TypeScript types and SWR API client"
```

**If Task Fails:**
1. **Type error:** Check that all types match the backend Pydantic models
2. **SWR import error:** Ensure `swr` is in `package.json` dependencies
3. **Rollback:** `rm frontend/src/lib/types.ts frontend/src/lib/api.ts`

---

### Task 9: Create environment config

**Files:**
- Create: `frontend/.env.local`
- Create: `frontend/.env.production`

**Prerequisites:**
- Task 6 completed

**Step 1: Create local env file**

Create `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Step 2: Create production/docker env file**

Create `frontend/.env.production`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Step 3: Add to .gitignore**

Ensure `frontend/.env.local` is in `frontend/.gitignore` (create-next-app already includes `.env*.local` in its `.gitignore`).

Run: `grep ".env" frontend/.gitignore`

**Expected output (should include):**
```
.env*.local
```

**Step 4: Commit**

```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
git add frontend/.env.production
git commit -m "feat(frontend): add environment configuration for API URL"
```

**If Task Fails:**
1. **File not in gitignore:** Add `.env*.local` to `frontend/.gitignore`
2. **Wrong API URL at runtime:** Change `NEXT_PUBLIC_API_URL` in `.env.local`

---

### Task 10: Create the root layout with sidebar

**Files:**
- Modify: `frontend/src/app/layout.tsx`
- Create: `frontend/src/components/sidebar.tsx`
- Modify: `frontend/src/app/globals.css` (clean up default styles)

**Prerequisites:**
- Tasks 7-8 completed (shadcn/ui components available)

**Step 1: Clean up globals.css**

Replace the content of `frontend/src/app/globals.css` with:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --background: 0 0% 98%;
    --foreground: 222.2 84% 4.9%;
    --card: 0 0% 100%;
    --card-foreground: 222.2 84% 4.9%;
    --popover: 0 0% 100%;
    --popover-foreground: 222.2 84% 4.9%;
    --primary: 221.2 83.2% 53.3%;
    --primary-foreground: 210 40% 98%;
    --secondary: 210 40% 96.1%;
    --secondary-foreground: 222.2 47.4% 11.2%;
    --muted: 210 40% 96.1%;
    --muted-foreground: 215.4 16.3% 46.9%;
    --accent: 210 40% 96.1%;
    --accent-foreground: 222.2 47.4% 11.2%;
    --destructive: 0 84.2% 60.2%;
    --destructive-foreground: 210 40% 98%;
    --border: 214.3 31.8% 91.4%;
    --input: 214.3 31.8% 91.4%;
    --ring: 221.2 83.2% 53.3%;
    --radius: 0.5rem;
    --sidebar: 222 47% 11%;
    --sidebar-foreground: 210 40% 98%;
  }
}

@layer base {
  * {
    @apply border-border;
  }
  body {
    @apply bg-background text-foreground antialiased;
    font-family: "Inter", system-ui, -apple-system, sans-serif;
  }
}
```

Note: If shadcn/ui init already set up CSS variables in `globals.css`, only add the `--sidebar` and `--sidebar-foreground` variables and the `font-family` line. Do not duplicate existing variables.

**Step 2: Create the sidebar component**

Create `frontend/src/components/sidebar.tsx`:

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Stethoscope,
  PlusCircle,
  Activity,
  Menu,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { useDoctors } from "@/lib/api";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/doctors", label: "Medicos", icon: Stethoscope },
];

function NavContent() {
  const pathname = usePathname();
  const { data: doctors } = useDoctors();
  const doctorCount = doctors?.length ?? 0;

  return (
    <div className="flex h-full flex-col">
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-6">
        <Activity className="h-7 w-7 text-blue-400" />
        <span className="text-lg font-bold text-white">AI Visibility</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-2">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
                isActive
                  ? "bg-white/10 text-white"
                  : "text-gray-400 hover:bg-white/5 hover:text-white"
              )}
            >
              <item.icon className="h-5 w-5" />
              {item.label}
              {item.label === "Medicos" && doctorCount > 0 && (
                <span className="ml-auto rounded-full bg-white/10 px-2 py-0.5 text-xs">
                  {doctorCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Bottom action */}
      <div className="p-4">
        <Link href="/doctors/new">
          <Button className="w-full gap-2" variant="secondary">
            <PlusCircle className="h-4 w-4" />
            Novo Medico
          </Button>
        </Link>
      </div>
    </div>
  );
}

export function Sidebar() {
  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden lg:fixed lg:inset-y-0 lg:z-50 lg:flex lg:w-64 lg:flex-col">
        <div className="flex grow flex-col overflow-y-auto bg-[hsl(var(--sidebar))] border-r border-white/10">
          <NavContent />
        </div>
      </aside>

      {/* Mobile header */}
      <div className="sticky top-0 z-40 flex items-center gap-4 border-b bg-white px-4 py-3 lg:hidden">
        <Sheet>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon">
              <Menu className="h-5 w-5" />
            </Button>
          </SheetTrigger>
          <SheetContent
            side="left"
            className="w-64 bg-[hsl(var(--sidebar))] p-0"
          >
            <NavContent />
          </SheetContent>
        </Sheet>
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-blue-600" />
          <span className="font-semibold">AI Visibility</span>
        </div>
      </div>
    </>
  );
}
```

**Step 3: Update the root layout**

Replace the content of `frontend/src/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "AI Visibility - iMedicina",
  description: "Diagnostico de visibilidade medica em IAs generativas",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR">
      <body className={inter.className}>
        <Sidebar />
        <main className="lg:pl-64">
          <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
            {children}
          </div>
        </main>
      </body>
    </html>
  );
}
```

**Step 4: Verify build**

Run: `cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility/frontend && npm run build 2>&1 | tail -10`

**Expected output:** Build completes without errors.

**Step 5: Commit**

```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
git add frontend/src/app/globals.css frontend/src/app/layout.tsx frontend/src/components/sidebar.tsx
git commit -m "feat(frontend): add sidebar navigation and root layout"
```

**If Task Fails:**
1. **Sheet component missing:** Run `npx shadcn@latest add sheet`
2. **CSS variable error:** Ensure `--sidebar` is defined in `globals.css`
3. **Build error:** Check import paths match your project structure
4. **Rollback:** `git checkout -- frontend/src/app/`

---

### Task 11: Create shared UI components (ScoreBadge, StatusBadge, ScoreGauge)

**Files:**
- Create: `frontend/src/components/score-badge.tsx`
- Create: `frontend/src/components/status-badge.tsx`
- Create: `frontend/src/components/score-gauge.tsx`

**Prerequisites:**
- Task 8 completed (types.ts exists)

**Step 1: Create ScoreBadge**

Create `frontend/src/components/score-badge.tsx`:

```tsx
import { Badge } from "@/components/ui/badge";
import { getScoreColor, getScoreLabel } from "@/lib/types";

interface ScoreBadgeProps {
  score: number | null | undefined;
  size?: "sm" | "md";
}

export function ScoreBadge({ score, size = "sm" }: ScoreBadgeProps) {
  if (score == null) return <Badge variant="outline">--</Badge>;

  const color = getScoreColor(score);
  const label = getScoreLabel(score);

  return (
    <Badge
      className={`${size === "md" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs"} font-semibold`}
      style={{ backgroundColor: `${color}20`, color, borderColor: `${color}40` }}
    >
      {Math.round(score)} - {label}
    </Badge>
  );
}
```

**Step 2: Create StatusBadge**

Create `frontend/src/components/status-badge.tsx`:

```tsx
import { Badge } from "@/components/ui/badge";
import type { RunStatus } from "@/lib/types";
import { Loader2, CheckCircle, XCircle, Clock } from "lucide-react";

const STATUS_CONFIG: Record<
  RunStatus,
  { label: string; variant: "default" | "secondary" | "destructive" | "outline"; icon: React.ComponentType<{ className?: string }> }
> = {
  pending: { label: "Pendente", variant: "outline", icon: Clock },
  running: { label: "Executando", variant: "default", icon: Loader2 },
  completed: { label: "Concluido", variant: "secondary", icon: CheckCircle },
  failed: { label: "Erro", variant: "destructive", icon: XCircle },
};

interface StatusBadgeProps {
  status: RunStatus;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status];
  const Icon = config.icon;

  return (
    <Badge variant={config.variant} className="gap-1">
      <Icon className={`h-3 w-3 ${status === "running" ? "animate-spin" : ""}`} />
      {config.label}
    </Badge>
  );
}
```

**Step 3: Create ScoreGauge (SVG donut)**

Create `frontend/src/components/score-gauge.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { getScoreColor, getScoreLabel } from "@/lib/types";

interface ScoreGaugeProps {
  score: number;
  size?: number;
}

export function ScoreGauge({ score, size = 192 }: ScoreGaugeProps) {
  const [animatedOffset, setAnimatedOffset] = useState(283);
  const color = getScoreColor(score);
  const label = getScoreLabel(score);
  const targetOffset = 283 * (1 - score / 100);

  useEffect(() => {
    const timeout = setTimeout(() => setAnimatedOffset(targetOffset), 100);
    return () => clearTimeout(timeout);
  }, [targetOffset]);

  return (
    <div className="flex flex-col items-center">
      <svg
        width={size}
        height={size}
        viewBox="0 0 100 100"
        className="drop-shadow-sm"
      >
        <circle
          cx="50"
          cy="50"
          r="45"
          fill="none"
          stroke="#e5e7eb"
          strokeWidth="8"
        />
        <circle
          cx="50"
          cy="50"
          r="45"
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray="283"
          strokeDashoffset={animatedOffset}
          transform="rotate(-90 50 50)"
          style={{ transition: "stroke-dashoffset 1s ease-in-out" }}
        />
        <text
          x="50"
          y="46"
          textAnchor="middle"
          fontSize="22"
          fontWeight="700"
          fill="#111827"
        >
          {Math.round(score)}
        </text>
        <text x="50" y="58" textAnchor="middle" fontSize="8" fill="#6b7280">
          /100
        </text>
        <text
          x="50"
          y="70"
          textAnchor="middle"
          fontSize="7"
          fontWeight="600"
          fill={color}
        >
          {label}
        </text>
      </svg>
    </div>
  );
}
```

**Step 4: Verify build**

Run: `cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility/frontend && npx tsc --noEmit 2>&1 | tail -5`

**Expected output:** No errors.

**Step 5: Commit**

```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
git add frontend/src/components/score-badge.tsx frontend/src/components/status-badge.tsx frontend/src/components/score-gauge.tsx
git commit -m "feat(frontend): add ScoreBadge, StatusBadge, and ScoreGauge components"
```

**If Task Fails:**
1. **Badge import error:** Ensure `npx shadcn@latest add badge` was run
2. **Type error on variant:** Check Badge component accepts the variants listed
3. **Rollback:** Delete the three component files

---

### Task 12: Code Review Checkpoint - Frontend Foundation

1. **Dispatch all 3 reviewers in parallel:**
   - REQUIRED SUB-SKILL: Use ring:requesting-code-review
   - All reviewers run simultaneously (ring:code-reviewer, ring:business-logic-reviewer, ring:security-reviewer)
   - Wait for all to complete

2. **Handle findings by severity (MANDATORY):**

**Critical/High/Medium Issues:**
- Fix immediately (do NOT add TODO comments for these severities)
- Re-run all 3 reviewers in parallel after fixes
- Repeat until zero Critical/High/Medium issues remain

**Low Issues:**
- Add `TODO(review):` comments in code at the relevant location

**Cosmetic/Nitpick Issues:**
- Add `FIXME(nitpick):` comments in code at the relevant location

3. **Proceed only when:**
   - Zero Critical/High/Medium issues remain
   - All Low issues have TODO(review): comments added
   - All Cosmetic issues have FIXME(nitpick): comments added

---

## Phase 3: Dashboard Page (Tasks 13-15)

### Task 13: Create the Dashboard page

**Files:**
- Modify: `frontend/src/app/page.tsx`

**Prerequisites:**
- Tasks 8, 10, 11 completed

**Step 1: Replace the default page**

Replace the content of `frontend/src/app/page.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useDoctors, useRuns } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { ScoreBadge } from "@/components/score-badge";
import { StatusBadge } from "@/components/status-badge";
import { Stethoscope, BarChart3, TrendingUp, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { RunStatus } from "@/lib/types";

export default function DashboardPage() {
  const { data: doctors, isLoading: doctorsLoading } = useDoctors();
  const { data: runs, isLoading: runsLoading } = useRuns();

  const doctorCount = doctors?.length ?? 0;
  const runCount = runs?.length ?? 0;
  const completedRuns = runs?.filter((r) => r.status === "completed") ?? [];
  const avgScore =
    completedRuns.length > 0
      ? completedRuns.reduce((sum, r) => sum + (r.score ?? 0), 0) /
        completedRuns.length
      : null;

  const topDoctors = (doctors ?? []).slice(0, 6);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Visao geral da visibilidade dos seus medicos em IAs
        </p>
      </div>

      {/* Stats row */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Medicos
            </CardTitle>
            <Stethoscope className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {doctorsLoading ? "..." : doctorCount}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Analises
            </CardTitle>
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {runsLoading ? "..." : runCount}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Score Medio
            </CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {avgScore != null ? `${Math.round(avgScore)}` : "--"}
            </div>
            {avgScore != null && (
              <ScoreBadge score={avgScore} />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Top doctors */}
      {topDoctors.length > 0 && (
        <div>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold">Medicos</h2>
            <Link href="/doctors">
              <Button variant="ghost" size="sm" className="gap-1">
                Ver todos <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {topDoctors.map((doc) => (
              <Link key={doc.id} href={`/doctors/${doc.id}`}>
                <Card className="transition-shadow hover:shadow-md cursor-pointer">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">{doc.name}</CardTitle>
                    <CardDescription>
                      {doc.specialty} - {doc.city}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="flex items-center justify-between">
                    <ScoreBadge score={doc.latest_score ?? null} />
                    <span className="text-xs text-muted-foreground">
                      {doc.run_count ?? 0} analise(s)
                    </span>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Recent runs table */}
      {(runs ?? []).length > 0 && (
        <div>
          <h2 className="mb-4 text-lg font-semibold">Analises Recentes</h2>
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Medico</TableHead>
                  <TableHead>Especialidade</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Data</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(runs ?? []).slice(0, 10).map((run) => (
                  <TableRow key={run.id}>
                    <TableCell>
                      <Link
                        href={`/analysis/${run.id}`}
                        className="font-medium text-blue-600 hover:underline"
                      >
                        {run.doctor_name}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {run.specialty}
                    </TableCell>
                    <TableCell>
                      <ScoreBadge score={run.score} />
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={run.status as RunStatus} />
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {run.created_at
                        ? new Date(run.created_at).toLocaleDateString("pt-BR")
                        : "--"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </div>
      )}

      {/* Empty state */}
      {!doctorsLoading && doctorCount === 0 && (
        <Card className="py-12 text-center">
          <CardContent>
            <Stethoscope className="mx-auto h-12 w-12 text-muted-foreground/50" />
            <h3 className="mt-4 text-lg font-semibold">
              Nenhum medico cadastrado
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Cadastre seu primeiro medico para iniciar uma analise de visibilidade.
            </p>
            <Link href="/doctors/new">
              <Button className="mt-4">Cadastrar Medico</Button>
            </Link>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
```

**Step 2: Verify build**

Run: `cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility/frontend && npm run build 2>&1 | tail -5`

**Expected output:** Build completes.

**Step 3: Commit**

```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
git add frontend/src/app/page.tsx
git commit -m "feat(frontend): build Dashboard page with stats, doctor cards, and runs table"
```

**If Task Fails:**
1. **Table component missing:** Run `npx shadcn@latest add table`
2. **Type errors:** Ensure `RunStatus` is imported from `@/lib/types`
3. **Rollback:** `git checkout -- frontend/src/app/page.tsx`

---

## Phase 4: Doctor Pages (Tasks 14-17)

### Task 14: Create Doctor List page

**Files:**
- Create: `frontend/src/app/doctors/page.tsx`

**Prerequisites:**
- Tasks 8, 10, 11 completed

**Step 1: Create the doctors directory and page**

Create `frontend/src/app/doctors/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import Link from "next/link";
import { useDoctors } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScoreBadge } from "@/components/score-badge";
import { PlusCircle, Search, MapPin, Award } from "lucide-react";

export default function DoctorsPage() {
  const { data: doctors, isLoading } = useDoctors();
  const [search, setSearch] = useState("");

  const filtered = (doctors ?? []).filter((doc) => {
    const q = search.toLowerCase();
    return (
      doc.name.toLowerCase().includes(q) ||
      doc.specialty.toLowerCase().includes(q) ||
      doc.city.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Medicos</h1>
          <p className="text-muted-foreground">
            {doctors?.length ?? 0} medico(s) cadastrado(s)
          </p>
        </div>
        <Link href="/doctors/new">
          <Button className="gap-2">
            <PlusCircle className="h-4 w-4" />
            Novo Medico
          </Button>
        </Link>
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Buscar por nome, especialidade ou cidade..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="pl-10"
        />
      </div>

      {/* Grid */}
      {isLoading ? (
        <div className="py-12 text-center text-muted-foreground">
          Carregando...
        </div>
      ) : filtered.length === 0 ? (
        <Card className="py-12 text-center">
          <CardContent>
            <p className="text-muted-foreground">Nenhum medico encontrado.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((doc) => (
            <Link key={doc.id} href={`/doctors/${doc.id}`}>
              <Card className="transition-shadow hover:shadow-md cursor-pointer h-full">
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <CardTitle className="text-base">{doc.name}</CardTitle>
                      <CardDescription>{doc.specialty}</CardDescription>
                    </div>
                    <ScoreBadge score={doc.latest_score ?? null} />
                  </div>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                    <MapPin className="h-3.5 w-3.5" />
                    {doc.city}
                    {doc.state && ` - ${doc.state}`}
                  </div>
                  {doc.crm && (
                    <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                      <Award className="h-3.5 w-3.5" />
                      CRM {doc.crm}/{doc.crm_state}
                    </div>
                  )}
                  <div className="text-xs text-muted-foreground">
                    {doc.run_count ?? 0} analise(s)
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
```

**Step 2: Verify build**

Run: `cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility/frontend && npm run build 2>&1 | tail -5`

**Expected output:** Build completes.

**Step 3: Commit**

```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
git add frontend/src/app/doctors/
git commit -m "feat(frontend): add Doctor List page with search filter and card grid"
```

---

### Task 15: Create Doctor Create page (form)

**Files:**
- Create: `frontend/src/app/doctors/new/page.tsx`

**Prerequisites:**
- Tasks 7-8 completed

**Step 1: Create the form page**

Create `frontend/src/app/doctors/new/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createDoctor } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ArrowLeft, Loader2 } from "lucide-react";
import Link from "next/link";

export default function NewDoctorPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const form = new FormData(e.currentTarget);
    try {
      const doctor = await createDoctor({
        name: form.get("name") as string,
        specialty: form.get("specialty") as string,
        city: form.get("city") as string,
        state: (form.get("state") as string) || undefined,
        neighborhood: (form.get("neighborhood") as string) || undefined,
        crm: (form.get("crm") as string) || undefined,
        crm_state: (form.get("crm_state") as string) || undefined,
      });
      router.push(`/doctors/${doctor.id}`);
    } catch (err) {
      setError("Erro ao cadastrar medico. Tente novamente.");
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div className="flex items-center gap-4">
        <Link href="/doctors">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Novo Medico</h1>
          <p className="text-muted-foreground">
            Cadastre um medico para analisar sua visibilidade em IAs
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Dados do Medico</CardTitle>
          <CardDescription>
            Preencha as informacoes do profissional
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="name">Nome completo *</Label>
                <Input
                  id="name"
                  name="name"
                  placeholder="Dr. Joao Silva"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="specialty">Especialidade *</Label>
                <Input
                  id="specialty"
                  name="specialty"
                  placeholder="Dermatologia"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="city">Cidade *</Label>
                <Input
                  id="city"
                  name="city"
                  placeholder="Campinas"
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="state">Estado</Label>
                <Input id="state" name="state" placeholder="SP" />
              </div>

              <div className="space-y-2">
                <Label htmlFor="neighborhood">Bairro</Label>
                <Input
                  id="neighborhood"
                  name="neighborhood"
                  placeholder="Cambuí"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="crm">CRM</Label>
                <Input id="crm" name="crm" placeholder="123456" />
              </div>

              <div className="space-y-2">
                <Label htmlFor="crm_state">UF do CRM</Label>
                <Input id="crm_state" name="crm_state" placeholder="SP" />
              </div>
            </div>

            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}

            <div className="flex justify-end gap-3 pt-2">
              <Link href="/doctors">
                <Button variant="outline" type="button">
                  Cancelar
                </Button>
              </Link>
              <Button type="submit" disabled={loading}>
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Cadastrar
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
```

**Step 2: Verify build**

Run: `cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility/frontend && npm run build 2>&1 | tail -5`

**Expected output:** Build completes.

**Step 3: Commit**

```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
git add frontend/src/app/doctors/new/
git commit -m "feat(frontend): add Doctor Create form page"
```

---

### Task 16: Create Doctor Detail page

**Files:**
- Create: `frontend/src/app/doctors/[id]/page.tsx`

**Prerequisites:**
- Tasks 8, 11 completed

**Step 1: Create the dynamic route page**

Create `frontend/src/app/doctors/[id]/page.tsx`:

```tsx
"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useDoctor, deleteDoctor, createRun } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScoreBadge } from "@/components/score-badge";
import { StatusBadge } from "@/components/status-badge";
import {
  ArrowLeft,
  Play,
  Trash2,
  MapPin,
  Award,
  Loader2,
  TrendingUp,
} from "lucide-react";
import type { RunStatus } from "@/lib/types";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

export default function DoctorDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const { data: doctor, isLoading, mutate } = useDoctor(id);
  const [runLoading, setRunLoading] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);

  async function handleNewRun() {
    setRunLoading(true);
    try {
      const result = await createRun(id);
      router.push(`/analysis/${result.run_id}`);
    } catch {
      setRunLoading(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Tem certeza que deseja remover este medico e todas as suas analises?")) {
      return;
    }
    setDeleteLoading(true);
    try {
      await deleteDoctor(id);
      router.push("/doctors");
    } catch {
      setDeleteLoading(false);
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!doctor) {
    return (
      <div className="py-12 text-center">
        <p className="text-muted-foreground">Medico nao encontrado.</p>
        <Link href="/doctors">
          <Button variant="link">Voltar para a lista</Button>
        </Link>
      </div>
    );
  }

  // Score trend data for chart
  const completedRuns = (doctor.runs ?? [])
    .filter((r) => r.status === "completed" && r.score != null)
    .reverse(); // oldest first for chart

  const chartData = completedRuns.map((r) => ({
    date: r.created_at
      ? new Date(r.created_at).toLocaleDateString("pt-BR", {
          day: "2-digit",
          month: "2-digit",
        })
      : "",
    score: r.score,
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link href="/doctors">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold tracking-tight">{doctor.name}</h1>
          <p className="text-muted-foreground">{doctor.specialty}</p>
        </div>
        <Button
          onClick={handleNewRun}
          disabled={runLoading}
          className="gap-2"
        >
          {runLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Play className="h-4 w-4" />
          )}
          Nova Analise
        </Button>
        <Button
          variant="destructive"
          size="icon"
          onClick={handleDelete}
          disabled={deleteLoading}
        >
          {deleteLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Trash2 className="h-4 w-4" />
          )}
        </Button>
      </div>

      {/* Profile card */}
      <Card>
        <CardContent className="flex flex-wrap items-center gap-6 pt-6">
          <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <MapPin className="h-4 w-4" />
            {doctor.city}
            {doctor.state && ` - ${doctor.state}`}
            {doctor.neighborhood && ` (${doctor.neighborhood})`}
          </div>
          {doctor.crm && (
            <div className="flex items-center gap-1.5">
              <Award className="h-4 w-4 text-muted-foreground" />
              <Badge variant="outline">
                CRM {doctor.crm}/{doctor.crm_state}
              </Badge>
            </div>
          )}
          <div className="text-sm text-muted-foreground">
            {doctor.runs?.length ?? 0} analise(s) realizadas
          </div>
        </CardContent>
      </Card>

      {/* Score trend chart */}
      {chartData.length >= 2 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <TrendingUp className="h-4 w-4" />
              Evolucao do Score
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                <XAxis dataKey="date" className="text-xs" />
                <YAxis domain={[0, 100]} className="text-xs" />
                <Tooltip />
                <Area
                  type="monotone"
                  dataKey="score"
                  stroke="#3b82f6"
                  fill="#3b82f6"
                  fillOpacity={0.1}
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Run history */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Historico de Analises</CardTitle>
        </CardHeader>
        <CardContent>
          {(doctor.runs ?? []).length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">
              Nenhuma analise realizada ainda.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Data</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(doctor.runs ?? []).map((run) => (
                  <TableRow key={run.id}>
                    <TableCell className="text-sm">
                      {run.created_at
                        ? new Date(run.created_at).toLocaleDateString("pt-BR", {
                            day: "2-digit",
                            month: "2-digit",
                            year: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })
                        : "--"}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={run.status as RunStatus} />
                    </TableCell>
                    <TableCell>
                      <ScoreBadge score={run.score} />
                    </TableCell>
                    <TableCell>
                      <Link href={`/analysis/${run.id}`}>
                        <Button variant="ghost" size="sm">
                          Ver
                        </Button>
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
```

**Step 2: Verify build**

Run: `cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility/frontend && npm run build 2>&1 | tail -5`

**Expected output:** Build completes.

**Step 3: Commit**

```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
git add frontend/src/app/doctors/\[id\]/
git commit -m "feat(frontend): add Doctor Detail page with score trend chart and run history"
```

**If Task Fails:**
1. **Recharts import error:** Ensure `recharts` is in `package.json`
2. **Dynamic route issue:** Ensure folder is named `[id]` exactly (with brackets)
3. **Rollback:** `rm -rf frontend/src/app/doctors/\[id\]/`

---

### Task 17: Code Review Checkpoint - Doctor Pages

1. **Dispatch all 3 reviewers in parallel:**
   - REQUIRED SUB-SKILL: Use ring:requesting-code-review
   - All reviewers run simultaneously (ring:code-reviewer, ring:business-logic-reviewer, ring:security-reviewer)
   - Wait for all to complete

2. **Handle findings by severity (MANDATORY):**

**Critical/High/Medium Issues:**
- Fix immediately
- Re-run all 3 reviewers in parallel after fixes

**Low Issues:**
- Add `TODO(review):` comments

**Cosmetic/Nitpick Issues:**
- Add `FIXME(nitpick):` comments

3. **Proceed only when:**
   - Zero Critical/High/Medium issues remain

---

## Phase 5: Analysis Page (Tasks 18-24)

### Task 18: Create Analysis page shell with polling

**Files:**
- Create: `frontend/src/app/analysis/[runId]/page.tsx`

**Prerequisites:**
- Tasks 8, 11 completed

**Step 1: Create the analysis page with loading state and polling**

Create `frontend/src/app/analysis/[runId]/page.tsx`:

```tsx
"use client";

import { use } from "react";
import { useRun, useRunStatus } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Loader2, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { OverviewTab } from "./overview-tab";
import { SimulationsTab } from "./simulations-tab";
import { CompetitorsTab } from "./competitors-tab";
import { ActionPlanTab } from "./action-plan-tab";

const PIPELINE_STEPS = [
  { key: "prompts", label: "Prompts" },
  { key: "simulator", label: "Consultas" },
  { key: "judge", label: "Analise" },
  { key: "scorer", label: "Score" },
];

function PipelineProgress({ progress }: { progress: string }) {
  const progressLower = progress.toLowerCase();
  const currentStep = progressLower.includes("score")
    ? 3
    : progressLower.includes("judg") || progressLower.includes("analis")
      ? 2
      : progressLower.includes("simul") || progressLower.includes("consult")
        ? 1
        : 0;

  return (
    <div className="flex items-center gap-2">
      {PIPELINE_STEPS.map((step, i) => (
        <div key={step.key} className="flex items-center gap-2">
          <div
            className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-medium ${
              i < currentStep
                ? "bg-green-100 text-green-700"
                : i === currentStep
                  ? "bg-blue-100 text-blue-700"
                  : "bg-gray-100 text-gray-400"
            }`}
          >
            {i < currentStep ? "\u2713" : i + 1}
          </div>
          <span
            className={`text-sm ${
              i <= currentStep ? "text-foreground" : "text-muted-foreground"
            }`}
          >
            {step.label}
          </span>
          {i < PIPELINE_STEPS.length - 1 && (
            <div
              className={`h-px w-8 ${
                i < currentStep ? "bg-green-300" : "bg-gray-200"
              }`}
            />
          )}
        </div>
      ))}
    </div>
  );
}

export default function AnalysisPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = use(params);
  const shouldPoll = true;
  const { data: statusData } = useRunStatus(
    runId,
    shouldPoll,
  );
  const isTerminal =
    statusData?.status === "completed" || statusData?.status === "failed";
  const { data: run, isLoading } = useRun(
    isTerminal ? runId : null,
  );

  // Show polling status while running
  if (!isTerminal && statusData) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Link href="/">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <h1 className="text-2xl font-bold tracking-tight">
            Analise em andamento
          </h1>
        </div>

        <Card className="py-12">
          <CardContent className="flex flex-col items-center gap-6">
            <Loader2 className="h-12 w-12 animate-spin text-blue-500" />
            <div className="text-center">
              <p className="text-lg font-semibold">Processando...</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {statusData.progress || "Iniciando pipeline..."}
              </p>
            </div>
            <PipelineProgress progress={statusData.progress ?? ""} />
          </CardContent>
        </Card>
      </div>
    );
  }

  if (isLoading || !run) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Error state
  if (run.status === "failed") {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Link href={`/doctors/${run.doctor_id}`}>
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <h1 className="text-2xl font-bold tracking-tight">Erro na Analise</h1>
        </div>
        <Card className="border-destructive">
          <CardContent className="pt-6">
            <p className="text-destructive">{run.error || "Erro desconhecido"}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Completed state with tabs
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link href={`/doctors/${run.doctor_id}`}>
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-bold tracking-tight">
            {run.doctor_name}
          </h1>
          <p className="text-muted-foreground">
            {run.specialty} - {run.city}
            {run.created_at &&
              ` - ${new Date(run.created_at).toLocaleDateString("pt-BR")}`}
          </p>
        </div>
      </div>

      <Tabs defaultValue="overview">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="overview">Visao Geral</TabsTrigger>
          <TabsTrigger value="simulations">Simulacoes</TabsTrigger>
          <TabsTrigger value="competitors">Concorrentes</TabsTrigger>
          <TabsTrigger value="actions">Plano de Acao</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-6">
          <OverviewTab run={run} />
        </TabsContent>
        <TabsContent value="simulations" className="mt-6">
          <SimulationsTab run={run} />
        </TabsContent>
        <TabsContent value="competitors" className="mt-6">
          <CompetitorsTab run={run} />
        </TabsContent>
        <TabsContent value="actions" className="mt-6">
          <ActionPlanTab run={run} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
```

**Step 2: Commit (tabs are imported but not yet created -- that's next)**

Note: Build will fail until Tasks 19-22 create the tab components. That is expected. Commit anyway to save progress.

```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
git add frontend/src/app/analysis/
git commit -m "feat(frontend): add Analysis page shell with SWR polling and tab navigation"
```

---

### Task 19: Create Overview Tab (score gauge, radar chart, prompt grid)

**Files:**
- Create: `frontend/src/app/analysis/[runId]/overview-tab.tsx`

**Prerequisites:**
- Tasks 11, 18 completed

**Step 1: Create the Overview Tab component**

Create `frontend/src/app/analysis/[runId]/overview-tab.tsx`:

```tsx
"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreGauge } from "@/components/score-gauge";
import { ScoreBadge } from "@/components/score-badge";
import { getScoreColor } from "@/lib/types";
import type { RunDetail, CitationType } from "@/lib/types";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
} from "recharts";

const DIMENSION_LABELS: Record<string, string> = {
  presence: "Presenca",
  quality: "Qualidade",
  position: "Posicao",
  competitive: "Competitivo",
};

const DIMENSION_WEIGHTS: Record<string, string> = {
  presence: "30%",
  quality: "40%",
  position: "20%",
  competitive: "10%",
};

const CITATION_BG: Record<CitationType, string> = {
  mentioned_by_name: "bg-green-400",
  mentioned_as_specialty: "bg-yellow-400",
  competitor_in_place: "bg-red-400",
  not_mentioned: "bg-gray-300",
};

const CITATION_SHORT: Record<CitationType, string> = {
  mentioned_by_name: "Nome",
  mentioned_as_specialty: "Esp.",
  competitor_in_place: "Conc.",
  not_mentioned: "--",
};

interface OverviewTabProps {
  run: RunDetail;
}

export function OverviewTab({ run }: OverviewTabProps) {
  const report = run.report;
  if (!report) return null;

  const score = report.score;
  const benchmark = run.benchmark ?? 30;

  const radarData = Object.entries(DIMENSION_LABELS).map(([key, label]) => ({
    dimension: label,
    value: score[key as keyof typeof score] as number,
    fullMark: 100,
  }));

  return (
    <div className="space-y-6">
      {/* Score + Benchmark row */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Score gauge */}
        <Card>
          <CardHeader>
            <CardTitle className="text-center text-base">
              AI Visibility Score
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col items-center">
            <ScoreGauge score={score.overall} size={200} />
            <p className="mt-4 text-sm text-muted-foreground">
              Media da especialidade ({run.specialty}):{" "}
              <strong>{benchmark}/100</strong>
            </p>
            {score.overall < benchmark ? (
              <p className="mt-1 text-sm text-red-600">
                {Math.round(benchmark - score.overall)} pontos abaixo da media
              </p>
            ) : (
              <p className="mt-1 text-sm text-green-600">
                {Math.round(score.overall - benchmark)} pontos acima da media
              </p>
            )}
          </CardContent>
        </Card>

        {/* Radar chart */}
        <Card>
          <CardHeader>
            <CardTitle className="text-center text-base">
              Dimensoes do Score
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <RadarChart data={radarData}>
                <PolarGrid />
                <PolarAngleAxis dataKey="dimension" className="text-xs" />
                <PolarRadiusAxis
                  angle={90}
                  domain={[0, 100]}
                  tick={false}
                />
                <Radar
                  name="Score"
                  dataKey="value"
                  stroke="#3b82f6"
                  fill="#3b82f6"
                  fillOpacity={0.2}
                  strokeWidth={2}
                />
              </RadarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Dimension bars */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Detalhamento por Dimensao</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {Object.entries(DIMENSION_LABELS).map(([key, label]) => {
            const value = score[key as keyof typeof score] as number;
            const color = getScoreColor(value);
            return (
              <div key={key}>
                <div className="mb-1 flex justify-between text-sm">
                  <span>
                    {label} ({DIMENSION_WEIGHTS[key]})
                  </span>
                  <span className="font-semibold">{Math.round(value)}</span>
                </div>
                <div className="h-2 rounded-full bg-gray-200">
                  <div
                    className="h-2 rounded-full transition-all duration-700"
                    style={{
                      width: `${value}%`,
                      backgroundColor: color,
                    }}
                  />
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>

      {/* Prompt performance grid (2x5) */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Performance por Prompt</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-5 gap-2">
            {report.verdicts.map((v) => {
              const prompt = report.prompts.find((p) => p.id === v.prompt_id);
              return (
                <div
                  key={v.prompt_id}
                  className={`${CITATION_BG[v.citation_type]} rounded-lg p-3 text-center text-white`}
                  title={prompt?.text ?? v.prompt_id}
                >
                  <div className="text-xs font-bold uppercase">
                    {v.prompt_id}
                  </div>
                  <div className="mt-1 text-xs opacity-90">
                    {CITATION_SHORT[v.citation_type]}
                  </div>
                  <div className="mt-0.5 text-xs opacity-75">
                    {Math.round(v.confidence * 100)}%
                  </div>
                </div>
              );
            })}
          </div>
          {/* Legend */}
          <div className="mt-4 flex flex-wrap gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <span className="inline-block h-3 w-3 rounded bg-green-400" />{" "}
              Citado por nome
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-3 w-3 rounded bg-yellow-400" />{" "}
              Especialidade
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-3 w-3 rounded bg-red-400" />{" "}
              Concorrente
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-3 w-3 rounded bg-gray-300" />{" "}
              Nao mencionado
            </span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
```

**Step 2: Commit**

```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
git add frontend/src/app/analysis/\[runId\]/overview-tab.tsx
git commit -m "feat(frontend): add Overview tab with score gauge, radar chart, and prompt grid"
```

---

### Task 20: Create Simulations Tab (chat cards with highlighting)

**Files:**
- Create: `frontend/src/app/analysis/[runId]/simulations-tab.tsx`

**Prerequisites:**
- Task 18 completed

**Step 1: Create the Simulations Tab**

Create `frontend/src/app/analysis/[runId]/simulations-tab.tsx`:

```tsx
"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ChevronDown, ChevronUp, ExternalLink, User, Bot } from "lucide-react";
import { CITATION_TYPE_CONFIG } from "@/lib/types";
import type { RunDetail } from "@/lib/types";

interface SimulationsTabProps {
  run: RunDetail;
}

function highlightNames(
  text: string,
  doctorName: string,
  competitors: string[]
): React.ReactNode {
  // Build a regex that matches doctor name or any competitor
  const allNames = [doctorName, ...competitors].filter(Boolean);
  if (allNames.length === 0) return text;

  const escaped = allNames.map((n) =>
    n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  );
  const regex = new RegExp(`(${escaped.join("|")})`, "gi");
  const parts = text.split(regex);

  return parts.map((part, i) => {
    const lower = part.toLowerCase();
    if (lower === doctorName.toLowerCase()) {
      return (
        <mark key={i} className="rounded bg-green-100 px-0.5 text-green-800">
          {part}
        </mark>
      );
    }
    if (competitors.some((c) => c.toLowerCase() === lower)) {
      return (
        <mark key={i} className="rounded bg-red-100 px-0.5 text-red-700">
          {part}
        </mark>
      );
    }
    return part;
  });
}

export function SimulationsTab({ run }: SimulationsTabProps) {
  const report = run.report;
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (!report) return null;

  return (
    <div className="space-y-4">
      {report.prompts.map((prompt) => {
        const response = report.responses.find(
          (r) => r.prompt_id === prompt.id
        );
        const verdict = report.verdicts.find(
          (v) => v.prompt_id === prompt.id
        );
        if (!response || !verdict) return null;

        const isExpanded = expandedId === prompt.id;
        const citConfig = CITATION_TYPE_CONFIG[verdict.citation_type];

        return (
          <Card
            key={prompt.id}
            className={`overflow-hidden border ${citConfig.bg}`}
          >
            {/* macOS-style header */}
            <CardHeader
              className="cursor-pointer bg-gray-800 px-4 py-2"
              onClick={() =>
                setExpandedId(isExpanded ? null : prompt.id)
              }
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {/* Traffic lights */}
                  <div className="flex gap-1.5">
                    <span className="h-3 w-3 rounded-full bg-red-500" />
                    <span className="h-3 w-3 rounded-full bg-yellow-500" />
                    <span className="h-3 w-3 rounded-full bg-green-500" />
                  </div>
                  <span className="text-xs font-medium text-gray-300">
                    {prompt.id.toUpperCase()} - {prompt.persona.replace(/_/g, " ")}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge
                    variant="outline"
                    className="border-gray-600 text-gray-300 text-xs"
                  >
                    {citConfig.label}
                  </Badge>
                  {verdict.position && (
                    <Badge
                      variant="outline"
                      className="border-gray-600 text-gray-300 text-xs"
                    >
                      #{verdict.position}
                    </Badge>
                  )}
                  <Badge
                    variant="outline"
                    className="border-gray-600 text-gray-300 text-xs"
                  >
                    {Math.round(verdict.confidence * 100)}%
                  </Badge>
                  {isExpanded ? (
                    <ChevronUp className="h-4 w-4 text-gray-400" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-gray-400" />
                  )}
                </div>
              </div>
            </CardHeader>

            {isExpanded && (
              <CardContent className="space-y-4 p-4">
                {/* Patient bubble */}
                <div className="flex gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100">
                    <User className="h-4 w-4 text-blue-600" />
                  </div>
                  <div className="rounded-2xl rounded-tl-sm bg-blue-50 px-4 py-3 text-sm">
                    {prompt.text}
                  </div>
                </div>

                {/* AI response bubble */}
                <div className="flex gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-100">
                    <Bot className="h-4 w-4 text-gray-600" />
                  </div>
                  <div className="flex-1 rounded-2xl rounded-tl-sm bg-white px-4 py-3 text-sm leading-relaxed shadow-sm">
                    <div className="whitespace-pre-wrap">
                      {highlightNames(
                        response.raw_text,
                        report.doctor.name,
                        verdict.competitors_named
                      )}
                    </div>

                    {/* Citations */}
                    {response.citations.length > 0 && (
                      <div className="mt-3 border-t pt-3">
                        <p className="mb-1 text-xs font-medium text-muted-foreground">
                          Fontes citadas:
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {response.citations.map((c, i) => (
                            <a
                              key={i}
                              href={c.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 rounded bg-gray-100 px-2 py-1 text-xs text-blue-600 hover:bg-gray-200"
                            >
                              <ExternalLink className="h-3 w-3" />
                              {c.title.length > 40
                                ? c.title.slice(0, 40) + "..."
                                : c.title}
                            </a>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Evidence quote */}
                <div className="ml-11 rounded-lg bg-gray-50 p-3 text-xs italic text-muted-foreground">
                  &ldquo;{verdict.evidence_quote}&rdquo;
                </div>
              </CardContent>
            )}
          </Card>
        );
      })}
    </div>
  );
}
```

**Step 2: Commit**

```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
git add frontend/src/app/analysis/\[runId\]/simulations-tab.tsx
git commit -m "feat(frontend): add Simulations tab with chat bubbles and name highlighting"
```

---

### Task 21: Create Competitors Tab (bar chart + table)

**Files:**
- Create: `frontend/src/app/analysis/[runId]/competitors-tab.tsx`

**Prerequisites:**
- Task 18 completed

**Step 1: Create the Competitors Tab**

Create `frontend/src/app/analysis/[runId]/competitors-tab.tsx`:

```tsx
"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { UserPlus, Users, TrendingDown, ArrowUpDown } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { createDoctor } from "@/lib/api";
import type { RunDetail } from "@/lib/types";

interface CompetitorsTabProps {
  run: RunDetail;
}

type SortKey = "name" | "count";
type SortDir = "asc" | "desc";

export function CompetitorsTab({ run }: CompetitorsTabProps) {
  const report = run.report;
  const router = useRouter();
  const [sortKey, setSortKey] = useState<SortKey>("count");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [registering, setRegistering] = useState<string | null>(null);

  const competitors = useMemo(() => {
    if (!report) return [];

    const counts: Record<string, number> = {};
    for (const v of report.verdicts) {
      for (const name of v.competitors_named) {
        counts[name] = (counts[name] ?? 0) + 1;
      }
    }

    return Object.entries(counts)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => {
        if (sortKey === "name") {
          return sortDir === "asc"
            ? a.name.localeCompare(b.name)
            : b.name.localeCompare(a.name);
        }
        return sortDir === "asc" ? a.count - b.count : b.count - a.count;
      });
  }, [report, sortKey, sortDir]);

  if (!report) return null;

  const totalPrompts = report.verdicts.length;
  const uniqueCompetitors = competitors.length;
  const topCompetitor = competitors[0];

  const chartData = competitors.slice(0, 10).map((c) => ({
    name: c.name.length > 20 ? c.name.slice(0, 20) + "..." : c.name,
    aparicoes: c.count,
  }));

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  async function handleRegister(competitorName: string) {
    setRegistering(competitorName);
    try {
      const doctor = await createDoctor({
        name: competitorName,
        specialty: run.specialty,
        city: run.city,
        state: run.state ?? undefined,
      });
      router.push(`/doctors/${doctor.id}`);
    } catch {
      setRegistering(null);
    }
  }

  return (
    <div className="space-y-6">
      {/* Summary stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="flex items-center gap-4 pt-6">
            <Users className="h-8 w-8 text-muted-foreground" />
            <div>
              <p className="text-2xl font-bold">{uniqueCompetitors}</p>
              <p className="text-sm text-muted-foreground">
                Concorrentes identificados
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center gap-4 pt-6">
            <TrendingDown className="h-8 w-8 text-red-400" />
            <div>
              <p className="text-2xl font-bold">
                {topCompetitor ? topCompetitor.count : 0}/{totalPrompts}
              </p>
              <p className="text-sm text-muted-foreground">
                {topCompetitor
                  ? `${topCompetitor.name} (mais citado)`
                  : "Nenhum concorrente"}
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex items-center gap-4 pt-6">
            <Badge variant="outline" className="text-lg px-3 py-1">
              {report.verdicts.filter(
                (v) => v.citation_type === "competitor_in_place"
              ).length}
              /{totalPrompts}
            </Badge>
            <div>
              <p className="text-sm text-muted-foreground">
                Prompts com concorrente dominante
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Bar chart */}
      {chartData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Top Concorrentes por Frequencia
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis type="number" domain={[0, totalPrompts]} />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={180}
                  className="text-xs"
                />
                <Tooltip />
                <Bar
                  dataKey="aparicoes"
                  fill="#3b82f6"
                  radius={[0, 4, 4, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Sortable table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Todos os Concorrentes</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead
                  className="cursor-pointer"
                  onClick={() => toggleSort("name")}
                >
                  <div className="flex items-center gap-1">
                    Nome <ArrowUpDown className="h-3 w-3" />
                  </div>
                </TableHead>
                <TableHead
                  className="cursor-pointer"
                  onClick={() => toggleSort("count")}
                >
                  <div className="flex items-center gap-1">
                    Aparicoes <ArrowUpDown className="h-3 w-3" />
                  </div>
                </TableHead>
                <TableHead>Frequencia</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {competitors.map((c) => (
                <TableRow key={c.name}>
                  <TableCell className="font-medium">{c.name}</TableCell>
                  <TableCell>
                    {c.count}/{totalPrompts}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-24 rounded-full bg-gray-200">
                        <div
                          className="h-2 rounded-full bg-blue-500"
                          style={{
                            width: `${(c.count / totalPrompts) * 100}%`,
                          }}
                        />
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {Math.round((c.count / totalPrompts) * 100)}%
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="outline"
                      size="sm"
                      className="gap-1"
                      disabled={registering === c.name}
                      onClick={() => handleRegister(c.name)}
                    >
                      <UserPlus className="h-3 w-3" />
                      Cadastrar
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
```

**Step 2: Commit**

```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
git add frontend/src/app/analysis/\[runId\]/competitors-tab.tsx
git commit -m "feat(frontend): add Competitors tab with bar chart, sortable table, and register action"
```

---

### Task 22: Create Action Plan Tab (recommendation cards)

**Files:**
- Create: `frontend/src/app/analysis/[runId]/action-plan-tab.tsx`

**Prerequisites:**
- Task 18 completed

**Step 1: Create the Action Plan Tab**

Create `frontend/src/app/analysis/[runId]/action-plan-tab.tsx`:

```tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, Lightbulb, TrendingUp } from "lucide-react";
import type { RunDetail } from "@/lib/types";

interface ActionPlanTabProps {
  run: RunDetail;
}

export function ActionPlanTab({ run }: ActionPlanTabProps) {
  const recommendations = run.recommendations ?? [];

  if (recommendations.length === 0) {
    return (
      <Card className="py-12 text-center">
        <CardContent>
          <TrendingUp className="mx-auto h-12 w-12 text-green-400" />
          <p className="mt-4 text-lg font-semibold">Excelente!</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Nenhuma recomendacao necessaria no momento.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="mb-2">
        <h2 className="text-lg font-semibold">Plano de Acao</h2>
        <p className="text-sm text-muted-foreground">
          {recommendations.length} recomendacao(es) baseadas na analise
        </p>
      </div>

      {recommendations.map((rec, i) => {
        // First recommendation is usually the most critical
        const isUrgent = i === 0 && recommendations.length > 1;

        return (
          <Card
            key={i}
            className={isUrgent ? "border-amber-200 bg-amber-50/50" : ""}
          >
            <CardContent className="flex gap-4 pt-6">
              <div
                className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${
                  isUrgent
                    ? "bg-amber-100 text-amber-600"
                    : "bg-blue-100 text-blue-600"
                }`}
              >
                {isUrgent ? (
                  <AlertTriangle className="h-5 w-5" />
                ) : (
                  <Lightbulb className="h-5 w-5" />
                )}
              </div>
              <div className="flex-1">
                <div className="mb-1 flex items-center gap-2">
                  <Badge variant={isUrgent ? "destructive" : "secondary"}>
                    {isUrgent ? "Prioridade Alta" : `Acao ${i + 1}`}
                  </Badge>
                </div>
                <p className="text-sm leading-relaxed">{rec}</p>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
```

**Step 2: Verify the full build now succeeds (all tabs exist)**

Run: `cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility/frontend && npm run build 2>&1 | tail -10`

**Expected output:** Build completes successfully with all routes listed.

**Step 3: Commit**

```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
git add frontend/src/app/analysis/\[runId\]/action-plan-tab.tsx
git commit -m "feat(frontend): add Action Plan tab with prioritized recommendation cards"
```

**If Task Fails:**
1. **Build fails:** Check that all 4 tab files exist in the `analysis/[runId]/` directory
2. **Import error:** Ensure each tab exports the correct named component
3. **Rollback:** Check build logs for specific error

---

### Task 23: Code Review Checkpoint - Analysis Page

1. **Dispatch all 3 reviewers in parallel:**
   - REQUIRED SUB-SKILL: Use ring:requesting-code-review
   - All reviewers run simultaneously (ring:code-reviewer, ring:business-logic-reviewer, ring:security-reviewer)
   - Wait for all to complete

2. **Handle findings by severity (MANDATORY):**

**Critical/High/Medium Issues:**
- Fix immediately
- Re-run all 3 reviewers in parallel after fixes

**Low Issues:**
- Add `TODO(review):` comments

**Cosmetic/Nitpick Issues:**
- Add `FIXME(nitpick):` comments

3. **Proceed only when:**
   - Zero Critical/High/Medium issues remain

---

## Phase 6: Docker Configuration (Tasks 24-26)

### Task 24: Create frontend Dockerfile

**Files:**
- Create: `frontend/Dockerfile`

**Prerequisites:**
- Frontend project exists (Task 6+)

**Step 1: Create the multi-stage Dockerfile**

Create `frontend/Dockerfile`:

```dockerfile
# ---------- Stage 1: Dependencies ----------
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---------- Stage 2: Build ----------
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# API URL must be set at build time for Next.js static optimization
# At runtime in Docker, the browser hits localhost:8000 via port mapping
ENV NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ---------- Stage 3: Runtime ----------
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
```

**Step 2: Enable standalone output in Next.js config**

Open `frontend/next.config.ts` (or `next.config.mjs`) and add the `output: "standalone"` option:

The file should look like:

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
```

**Step 3: Create .dockerignore**

Create `frontend/.dockerignore`:

```
node_modules
.next
.git
*.md
.env*.local
```

**Step 4: Verify Dockerfile syntax**

Run: `docker build -t ai-visibility-frontend frontend/ 2>&1 | tail -5`

**Expected output:**
```
Successfully built <hash>
Successfully tagged ai-visibility-frontend:latest
```

**Step 5: Commit**

```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
git add frontend/Dockerfile frontend/.dockerignore frontend/next.config.ts
git commit -m "feat(frontend): add multi-stage Dockerfile with standalone output"
```

**If Task Fails:**
1. **Build fails in deps stage:** Check `package-lock.json` exists
2. **Standalone output not found:** Ensure `output: "standalone"` is in `next.config.ts`
3. **Rollback:** `rm frontend/Dockerfile frontend/.dockerignore`

---

### Task 25: Update docker-compose.yml with frontend service

**Files:**
- Modify: `docker-compose.yml`

**Prerequisites:**
- Task 24 completed

**Step 1: Add the frontend service**

Add the `frontend` service to `docker-compose.yml`. The complete file should be:

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ai_visibility
      POSTGRES_USER: app
      POSTGRES_PASSWORD: dev
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d ai_visibility"]
      interval: 5s
      timeout: 3s
      retries: 5

  app:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://app:dev@db:5432/ai_visibility
    env_file:
      - .env

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      - app
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000

volumes:
  pgdata:
```

**Step 2: Verify compose config**

Run: `cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility && docker compose config --services`

**Expected output:**
```
db
app
frontend
```

**Step 3: Commit**

```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
git add docker-compose.yml
git commit -m "feat(docker): add frontend service to docker-compose"
```

**If Task Fails:**
1. **YAML syntax error:** Validate with `docker compose config`
2. **Rollback:** `git checkout -- docker-compose.yml`

---

### Task 26: Full integration test

**Prerequisites:**
- All previous tasks completed

**Step 1: Build and start everything**

Run: `cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility && docker compose up -d --build 2>&1 | tail -10`

**Expected output:**
```
Creating ... done
```

All 3 services should be running.

**Step 2: Verify all services are up**

Run: `docker compose ps`

**Expected output:** 3 services (db, app, frontend) with status "Up" or "running".

**Step 3: Verify API works**

Run: `curl -s http://localhost:8000/api/doctors | python3 -m json.tool | head -5`

**Expected output:** JSON array.

**Step 4: Verify frontend works**

Run: `curl -s -o /dev/null -w "%{http_code}" http://localhost:3000`

**Expected output:**
```
200
```

**Step 5: Seed example data and verify**

Run:
```bash
cd /Users/raphaquintan/Documents/personal_projects/ai_doctor_visibility
for f in examples/*/report.json; do
  curl -s -X POST http://localhost:8000/api/seed -H "Content-Type: application/json" -d "{\"report\": $(cat $f)}" | python3 -m json.tool
done
```

**Expected output:** 3 JSON responses with `doctor_id`, `run_id`, `score`.

**Step 6: Verify dashboard shows data**

Run: `curl -s http://localhost:8000/api/doctors | python3 -c "import sys, json; data=json.load(sys.stdin); print(f'{len(data)} doctors loaded')"`

**Expected output:**
```
3 doctors loaded
```

**If Task Fails:**
1. **Frontend can't reach API:** Check CORS configuration and API URL
2. **Database errors:** Run `docker compose logs app` to check connection
3. **Build errors:** Run `docker compose logs frontend` for Next.js logs
4. **Full reset:** `docker compose down -v && docker compose up -d --build`

---

### Task 27: Final Code Review Checkpoint

1. **Dispatch all 3 reviewers in parallel:**
   - REQUIRED SUB-SKILL: Use ring:requesting-code-review
   - All reviewers run simultaneously (ring:code-reviewer, ring:business-logic-reviewer, ring:security-reviewer)
   - Wait for all to complete

2. **Handle findings by severity (MANDATORY):**

**Critical/High/Medium Issues:**
- Fix immediately

**Low Issues:**
- Add `TODO(review):` comments

**Cosmetic/Nitpick Issues:**
- Add `FIXME(nitpick):` comments

3. **Proceed only when:**
   - Zero Critical/High/Medium issues remain

---

## Summary

| Phase | Tasks | Estimated Time | Description |
|-------|-------|----------------|-------------|
| 1 - Backend API | 1-5 | 20 min | JSON API routes, DB function, CORS, verification |
| 2 - Frontend Setup | 6-12 | 30 min | Next.js scaffold, shadcn/ui, types, layout, shared components |
| 3 - Dashboard | 13 | 10 min | Dashboard page with stats, cards, table |
| 4 - Doctor Pages | 14-17 | 20 min | List, Create, Detail pages with score trend chart |
| 5 - Analysis Page | 18-23 | 35 min | 4 tabs: Overview, Simulations, Competitors, Action Plan |
| 6 - Docker | 24-27 | 15 min | Frontend Dockerfile, compose config, integration test |
| **Total** | **27 tasks** | **~130 min** | |

### Files Created/Modified

**Backend (modified):**
- `ai_visibility/web/api_routes.py` (new)
- `ai_visibility/web/db.py` (add `list_doctors_with_counts`)
- `ai_visibility/web/app.py` (add CORS + API router)
- `docker-compose.yml` (add frontend service)

**Frontend (all new):**
- `frontend/` - entire Next.js project
- `frontend/src/lib/types.ts` - TypeScript types
- `frontend/src/lib/api.ts` - SWR hooks + mutations
- `frontend/src/components/sidebar.tsx` - navigation
- `frontend/src/components/score-badge.tsx` - reusable badge
- `frontend/src/components/status-badge.tsx` - run status badge
- `frontend/src/components/score-gauge.tsx` - SVG donut gauge
- `frontend/src/app/page.tsx` - Dashboard
- `frontend/src/app/doctors/page.tsx` - Doctor list
- `frontend/src/app/doctors/new/page.tsx` - Doctor create form
- `frontend/src/app/doctors/[id]/page.tsx` - Doctor detail + chart
- `frontend/src/app/analysis/[runId]/page.tsx` - Analysis shell
- `frontend/src/app/analysis/[runId]/overview-tab.tsx` - Score + radar + grid
- `frontend/src/app/analysis/[runId]/simulations-tab.tsx` - Chat cards
- `frontend/src/app/analysis/[runId]/competitors-tab.tsx` - Bar chart + table
- `frontend/src/app/analysis/[runId]/action-plan-tab.tsx` - Recommendations
- `frontend/Dockerfile` - Multi-stage build
- `frontend/.dockerignore`
