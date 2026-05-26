"""Prompt cache backed by PostgreSQL.

Reuses prompts across doctors of the same specialty × city.
Aligned with PRD P0.7: shared cache per specialty × city, cost target < R$30/doctor/month.

Falls back to in-memory dict when no database is available (e.g. CLI-only usage).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from ai_visibility.config import settings

logger = logging.getLogger(__name__)

# In-memory fallback for CLI usage (no PostgreSQL)
_mem_cache: dict[str, object] = {}


def cache_key(specialty: str, city: str, neighborhood: str | None = None) -> str:
    parts = [specialty.lower().strip(), city.lower().strip()]
    if neighborhood:
        parts.append(neighborhood.lower().strip())
    return ":".join(parts)


def _get_pool():
    """Try to get the PostgreSQL pool. Returns None if not initialized."""
    try:
        from ai_visibility.web.db import get_pool

        return get_pool()
    except (ImportError, RuntimeError):
        return None


def get_cached(key: str) -> object | None:
    pool = _get_pool()
    if pool is None:
        return _mem_cache.get(key)

    with pool.connection() as conn:
        row = conn.execute(
            """
            SELECT value FROM prompt_cache
            WHERE key = %s AND expires_at > now()
            """,
            (key,),
        ).fetchone()

    if row is None:
        return None
    return row["value"]


def set_cached(key: str, value: object) -> None:
    pool = _get_pool()
    if pool is None:
        _mem_cache[key] = value
        return

    ttl_seconds = settings.cache_ttl_seconds
    with pool.connection() as conn:
        conn.execute(
            """
            INSERT INTO prompt_cache (key, value, expires_at)
            VALUES (%s, %s::jsonb, now() + make_interval(secs => %s))
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, expires_at = EXCLUDED.expires_at
            """,
            (key, json.dumps(value), ttl_seconds),
        )
