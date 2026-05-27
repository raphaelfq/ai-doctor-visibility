"""PostgreSQL database layer — connection pool, schema, and CRUD operations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS doctors (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL,
    specialty    TEXT NOT NULL,
    city         TEXT NOT NULL,
    state        TEXT,
    neighborhood TEXT,
    crm          TEXT,
    crm_state    TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS runs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id    UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    status       TEXT NOT NULL DEFAULT 'pending',
    score        REAL,
    error        TEXT,
    report_json  JSONB,
    progress     TEXT DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_runs_doctor_id ON runs(doctor_id);
CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at DESC);

CREATE TABLE IF NOT EXISTS prompt_cache (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);
"""


def init_pool(database_url: str) -> ConnectionPool:
    """Create and return a connection pool. Also runs schema migration."""
    global _pool
    _pool = ConnectionPool(
        conninfo=database_url,
        min_size=2,
        max_size=10,
        kwargs={"row_factory": dict_row},
    )
    _pool.wait()
    with _pool.connection() as conn:
        conn.execute(SCHEMA_SQL)
    return _pool


def get_pool() -> ConnectionPool:
    """Return the global pool. Raises if not initialized."""
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_pool() first.")
    return _pool


def close_pool() -> None:
    """Close the global pool."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


# ---------------------------------------------------------------------------
# Doctors CRUD
# ---------------------------------------------------------------------------


def create_doctor(
    *,
    name: str,
    specialty: str,
    city: str,
    state: str | None = None,
    neighborhood: str | None = None,
    crm: str | None = None,
    crm_state: str | None = None,
) -> str:
    """Insert a doctor and return its UUID string."""
    doctor_id = str(uuid.uuid4())
    with get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO doctors (id, name, specialty, city, state, neighborhood, crm, crm_state)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (doctor_id, name, specialty, city, state, neighborhood, crm, crm_state),
        )
    return doctor_id


def get_doctor(doctor_id: str) -> dict[str, Any] | None:
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT * FROM doctors WHERE id = %s", (doctor_id,)
        ).fetchone()
    return dict(row) if row else None


def list_doctors(limit: int = 100) -> list[dict[str, Any]]:
    with get_pool().connection() as conn:
        rows = conn.execute(
            "SELECT * FROM doctors ORDER BY created_at DESC LIMIT %s", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_doctor(doctor_id: str) -> None:
    with get_pool().connection() as conn:
        conn.execute("DELETE FROM doctors WHERE id = %s", (doctor_id,))


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


# ---------------------------------------------------------------------------
# Runs CRUD
# ---------------------------------------------------------------------------


def has_active_run(doctor_id: str) -> bool:
    """Check if a doctor has any pending or running runs."""
    with get_pool().connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM runs WHERE doctor_id = %s AND status IN ('pending', 'running') LIMIT 1",
            (doctor_id,),
        ).fetchone()
    return row is not None


def create_run(*, doctor_id: str) -> str:
    """Insert a pending run and return its UUID string."""
    run_id = str(uuid.uuid4())
    with get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO runs (id, doctor_id) VALUES (%s, %s)",
            (run_id, doctor_id),
        )
    return run_id


def get_run(run_id: str) -> dict[str, Any] | None:
    with get_pool().connection() as conn:
        row = conn.execute(
            """
            SELECT r.*, d.name AS doctor_name, d.specialty, d.city, d.state,
                   d.neighborhood, d.crm, d.crm_state
            FROM runs r JOIN doctors d ON r.doctor_id = d.id
            WHERE r.id = %s
            """,
            (run_id,),
        ).fetchone()
    return dict(row) if row else None


def list_runs_for_doctor(
    doctor_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM runs WHERE doctor_id = %s
            ORDER BY created_at DESC LIMIT %s
            """,
            (doctor_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def list_recent_runs(limit: int = 20) -> list[dict[str, Any]]:
    with get_pool().connection() as conn:
        rows = conn.execute(
            """
            SELECT r.*, d.name AS doctor_name, d.specialty, d.city
            FROM runs r JOIN doctors d ON r.doctor_id = d.id
            ORDER BY r.created_at DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_run_status(run_id: str, *, status: str, **kwargs: Any) -> None:
    """Update run status and any extra fields (score, report_json, error, progress, completed_at)."""
    allowed = {"score", "report_json", "error", "progress", "completed_at"}
    sets = ["status = %s"]
    vals: list[Any] = [status]
    for key, val in kwargs.items():
        if key not in allowed:
            continue
        sets.append(f"{key} = %s")
        vals.append(val)
    vals.append(run_id)
    with get_pool().connection() as conn:
        conn.execute(
            f"UPDATE runs SET {', '.join(sets)} WHERE id = %s",
            vals,
        )
