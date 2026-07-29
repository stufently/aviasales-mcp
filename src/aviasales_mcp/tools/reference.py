"""MCP tools for reference/lookup data (airlines, airports, cities, countries).

These datasets are static and very large — ``airports.json`` alone is ~2.7 MB
across 10k entries, which is far past what any model can hold in context. So the
tools cache each dataset per process and return a filtered, trimmed slice rather
than the whole file.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from aviasales_mcp.api.client import TravelpayoutsError, get

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 500

# Reference data changes on the order of weeks; one download per process is plenty.
CACHE_TTL_SECONDS = 24 * 60 * 60

# Per-language name blobs and Russian grammatical cases dwarf every field that is
# actually useful, and `name` already carries the English name.
_DROP_FIELDS = frozenset({"name_translations", "cases"})

_cache: dict[str, tuple[float, list[dict]]] = {}


def _reset_cache() -> None:
    """Drop the in-process dataset cache (used by tests)."""
    _cache.clear()


async def _dataset(path: str) -> list[dict]:
    """Fetch a reference dataset, reusing the cached copy when it is still fresh."""
    cached = _cache.get(path)
    if cached is not None and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    try:
        data = await get(path)
    except TravelpayoutsError:
        # Airport and city codes barely change. A stale answer beats no answer.
        if cached is not None:
            logger.warning("Serving stale %s — refresh failed", path)
            return cached[1]
        raise

    items = [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
    _cache[path] = (time.monotonic(), items)
    return items


def _matches(item: dict, needle: str) -> bool:
    if needle == str(item.get("code", "")).lower():
        return True
    if needle == str(item.get("city_code", "")).lower():
        return True
    return needle in str(item.get("name", "")).lower()


def _slim(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in _DROP_FIELDS}


def _respond(items: list[dict], search: str | None, limit: int) -> dict[str, Any]:
    limit = max(1, min(limit, MAX_LIMIT))
    needle = (search or "").strip().lower()
    if needle:
        items = [item for item in items if _matches(item, needle)]
    page = [_slim(item) for item in items[:limit]]
    return {
        "total": len(items),
        "returned": len(page),
        "truncated": len(items) > len(page),
        "data": page,
    }


def _error(exc: Exception) -> dict[str, Any]:
    return {"error": str(exc), "total": 0, "returned": 0, "truncated": False, "data": []}


async def _lookup(path: str, search: str | None, limit: int) -> dict[str, Any]:
    try:
        items = await _dataset(path)
    except TravelpayoutsError as exc:
        # Covers RateLimitError too — an exception escaping here would reach the
        # model as a protocol error instead of something it can act on.
        return _error(exc)
    return _respond(items, search, limit)


async def lookup_airlines(search: str | None = None, limit: int = DEFAULT_LIMIT) -> dict:
    """Look up airlines by name or IATA code.

    Args:
        search: Airline name substring or exact IATA code (e.g. "aeroflot", "SU").
            Omit to list airlines from the start of the dataset.
        limit: Max results to return (1-500, default 50).

    Returns:
        Dict with "total" (matches found), "returned", "truncated" and "data"
        (airline objects: name, code, is_lowcost).
    """
    return await _lookup("/data/en/airlines.json", search, limit)


async def lookup_airports(search: str | None = None, limit: int = DEFAULT_LIMIT) -> dict:
    """Look up airports by name, IATA code, or city code.

    The full dataset is ~10k airports, so always pass `search` — an unfiltered
    call just returns the first `limit` entries in dataset order.

    Args:
        search: Airport name substring, exact IATA code, or city code
            (e.g. "heathrow", "LHR", "MOW").
        limit: Max results to return (1-500, default 50).

    Returns:
        Dict with "total", "returned", "truncated" and "data" (airport objects:
        code, name, city_code, country_code, coordinates, time_zone, flightable).
    """
    return await _lookup("/data/en/airports.json", search, limit)


async def lookup_cities(search: str | None = None, limit: int = DEFAULT_LIMIT) -> dict:
    """Look up cities by name or IATA code — use this to turn a city name into a code.

    The full dataset is ~9.6k cities, so always pass `search`.

    Args:
        search: City name substring or exact IATA code (e.g. "bangkok", "BKK").
        limit: Max results to return (1-500, default 50).

    Returns:
        Dict with "total", "returned", "truncated" and "data" (city objects:
        code, name, country_code, coordinates, time_zone).
    """
    return await _lookup("/data/en/cities.json", search, limit)


async def lookup_countries(search: str | None = None, limit: int = DEFAULT_LIMIT) -> dict:
    """Look up countries by name or two-letter code.

    Args:
        search: Country name substring or exact code (e.g. "thailand", "TH").
        limit: Max results to return (1-500, default 50).

    Returns:
        Dict with "total", "returned", "truncated" and "data" (country objects:
        code, name, currency).
    """
    return await _lookup("/data/en/countries.json", search, limit)
