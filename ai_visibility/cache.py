"""Disk cache for reusing prompts across doctors of the same specialty × city.

Aligned with PRD P0.7: shared cache per specialty × city, cost target < R$30/doctor/month.
"""

from pathlib import Path

import diskcache

from ai_visibility.config import settings


def _get_cache() -> diskcache.Cache:
    cache_dir = Path(settings.cache_dir) / "ai-visibility"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return diskcache.Cache(str(cache_dir))


def cache_key(specialty: str, city: str, neighborhood: str | None = None) -> str:
    parts = [specialty.lower().strip(), city.lower().strip()]
    if neighborhood:
        parts.append(neighborhood.lower().strip())
    return ":".join(parts)


def get_cached(key: str) -> object | None:
    cache = _get_cache()
    return cache.get(key)


def set_cached(key: str, value: object) -> None:
    cache = _get_cache()
    cache.set(key, value, expire=settings.cache_ttl_seconds)
