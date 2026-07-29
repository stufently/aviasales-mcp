"""MCP tools for reference/lookup data (airlines, airports, cities, countries).

These datasets are static and very large — ``airports.json`` alone is ~2.5 MB
across 10k entries, which is far past what any model can hold in context. So the
tools cache each dataset per process and return a filtered, trimmed slice rather
than the whole file.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Annotated, Any

from pydantic import Field

from aviasales_mcp import validation
from aviasales_mcp.api.client import TravelpayoutsError, get
from aviasales_mcp.config import settings
from aviasales_mcp.tools.responses import guard

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 500

# Reference data changes on the order of weeks; one download per process is plenty.
CACHE_TTL_SECONDS = 24 * 60 * 60

EARTH_RADIUS_KM = 6371.0088

# Per-language name blobs and Russian grammatical cases dwarf every field that is
# actually useful, and `name` already carries the localized name.
_DROP_FIELDS = frozenset({"name_translations", "cases"})

_LOOKUP_HINT = (
    "Nothing matched. Try a shorter substring, the IATA code itself, or a different "
    "locale — dataset names are in the requested language only."
)

_cache: dict[str, tuple[float, list[dict]]] = {}


def _reset_cache() -> None:
    """Drop the in-process dataset cache (used by tests)."""
    _cache.clear()


def _error(message: str, hint: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "error",
        "error": message,
        "total": 0,
        "returned": 0,
        "truncated": False,
        "data": [],
    }
    if hint:
        payload["hint"] = hint
    return payload


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


def _dataset_path(name: str, locale: str | None) -> str:
    return f"/data/{locale or 'en'}/{name}.json"


def _rank(item: dict, needle: str) -> int:
    """How well an entry matches, lower is better.

    The datasets are in no meaningful order, so slicing the first `limit`
    substring matches used to bury Heathrow under whatever heliport happened to
    be listed first.
    """
    code = str(item.get("code", "")).lower()
    city_code = str(item.get("city_code", "")).lower()
    name = str(item.get("name", "")).lower()
    if code == needle:
        return 0
    if city_code == needle:
        return 1
    if name == needle:
        return 2
    if name.startswith(needle):
        return 3
    return 4


def _matches(item: dict, needle: str) -> bool:
    if needle == str(item.get("code", "")).lower():
        return True
    if needle == str(item.get("city_code", "")).lower():
        return True
    return needle in str(item.get("name", "")).lower()


def _is_flightable(item: dict) -> bool:
    """Whether an entry can actually be flown to.

    ``flightable`` is on airports, ``has_flightable_airport`` on cities; datasets
    without either (airlines, countries) are all treated as usable so their order
    is untouched.
    """
    for key in ("flightable", "has_flightable_airport"):
        if key in item:
            return bool(item[key])
    return True


def _slim(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in _DROP_FIELDS}


def _respond(items: list[dict], search: str | None, limit: int) -> dict[str, Any]:
    limit = max(1, min(limit, MAX_LIMIT))
    needle = (search or "").strip().lower()
    if needle:
        items = [item for item in items if _matches(item, needle)]
        items = sorted(items, key=lambda item: (_rank(item, needle), not _is_flightable(item)))
    page = [_slim(item) for item in items[:limit]]
    payload: dict[str, Any] = {
        "status": "ok",
        "total": len(items),
        "returned": len(page),
        "truncated": len(items) > len(page),
        "data": page,
    }
    if not page:
        payload["hint"] = _LOOKUP_HINT
    return payload


async def _lookup(name: str, search: str | None, limit: int, locale: str | None) -> dict[str, Any]:
    locale = validation.two_letter_code(locale, "locale", settings.aviasales_locale)
    items = await _dataset(_dataset_path(name, locale))
    return _respond(items, search, limit)


@guard(_error, hint=_LOOKUP_HINT)
async def lookup_airlines(
    search: str | None = None,
    limit: Annotated[int, Field(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    locale: str | None = None,
) -> dict:
    """Look up airlines by name or IATA code.

    Args:
        search: Airline name substring or exact IATA code (e.g. "aeroflot", "SU").
            Omit to list airlines from the start of the dataset.
        limit: Max results to return (1-500, default 50).
        locale: 2-letter locale for names (e.g. "en", "ru"). Defaults to the
            server's locale.

    Returns:
        Dict with "status", "total" (matches found), "returned", "truncated" and
        "data" (airline objects: name, code, is_lowcost).
    """
    return await _lookup("airlines", search, limit, locale)


@guard(_error, hint=_LOOKUP_HINT)
async def lookup_airports(
    search: str | None = None,
    limit: Annotated[int, Field(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    locale: str | None = None,
) -> dict:
    """Look up airports by name, IATA code, or city code.

    The full dataset is ~10k airports, so always pass `search` — an unfiltered
    call just returns the first `limit` entries in dataset order. Results are
    ranked: exact code, then exact city code, then name matches, with airports
    you cannot actually fly to last. To search by location instead of by name,
    use `find_nearest_airports`.

    Args:
        search: Airport name substring, exact IATA code, or city code
            (e.g. "heathrow", "LHR", "MOW").
        limit: Max results to return (1-500, default 50).
        locale: 2-letter locale for names (e.g. "en", "ru"). Defaults to the
            server's locale.

    Returns:
        Dict with "status", "total", "returned", "truncated" and "data" (airport
        objects: code, name, city_code, country_code, coordinates, time_zone,
        flightable).
    """
    return await _lookup("airports", search, limit, locale)


@guard(_error, hint=_LOOKUP_HINT)
async def lookup_cities(
    search: str | None = None,
    limit: Annotated[int, Field(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    locale: str | None = None,
) -> dict:
    """Look up cities by name or IATA code — use this to turn a city name into a code.

    Every flight tool takes IATA codes, so this is usually the first call when
    the user names a place. The full dataset is ~9.6k cities, so always pass
    `search`. Names are only available in the requested locale: searching
    "Мюнхен" needs locale="ru".

    Args:
        search: City name substring or exact IATA code (e.g. "bangkok", "BKK").
        limit: Max results to return (1-500, default 50).
        locale: 2-letter locale for names (e.g. "en", "ru"). Defaults to the
            server's locale.

    Returns:
        Dict with "status", "total", "returned", "truncated" and "data" (city
        objects: code, name, country_code, coordinates, time_zone).
    """
    return await _lookup("cities", search, limit, locale)


@guard(_error, hint=_LOOKUP_HINT)
async def lookup_countries(
    search: str | None = None,
    limit: Annotated[int, Field(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    locale: str | None = None,
) -> dict:
    """Look up countries by name or two-letter code.

    Args:
        search: Country name substring or exact code (e.g. "thailand", "TH").
        limit: Max results to return (1-500, default 50).
        locale: 2-letter locale for names (e.g. "en", "ru"). Defaults to the
            server's locale.

    Returns:
        Dict with "status", "total", "returned", "truncated" and "data" (country
        objects: code, name, currency).
    """
    return await _lookup("countries", search, limit, locale)


def _coordinates(item: dict) -> tuple[float, float] | None:
    coords = item.get("coordinates")
    if not isinstance(coords, dict):
        return None
    lat, lon = coords.get("lat"), coords.get("lon")
    if isinstance(lat, int | float) and isinstance(lon, int | float):
        return float(lat), float(lon)
    return None


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi = p2 - p1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _resolve_place(
    query: str, cities: list[dict], airports: list[dict]
) -> tuple[tuple[float, float], dict] | None:
    """Turn a place name or code into coordinates, preferring cities over airports.

    Resolution happens against the datasets we already cache, so there is no
    third-party geocoder in the loop and nothing new to rate-limit.
    """
    needle = query.strip().lower()
    if not needle:
        return None
    for dataset, kind in ((cities, "city"), (airports, "airport")):
        for rank in range(5):
            for item in dataset:
                if not _matches(item, needle) or _rank(item, needle) != rank:
                    continue
                coords = _coordinates(item)
                if coords is None:
                    continue
                return coords, {
                    "matched": kind,
                    "code": item.get("code", ""),
                    "name": item.get("name", ""),
                    "country_code": item.get("country_code", ""),
                    "coordinates": {"lat": coords[0], "lon": coords[1]},
                }
    return None


@guard(_error, hint=_LOOKUP_HINT)
async def find_nearest_airports(
    near: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 5,
    max_distance_km: Annotated[float | None, Field(gt=0)] = None,
    flightable_only: bool = True,
    locale: str | None = None,
) -> dict:
    """Find the airports closest to a place, by distance.

    Answers "which airport should I fly into for Pattaya?" — a question
    `lookup_airports` cannot, because it only matches on name and the nearest
    airport is rarely named after the town. Feed the returned `city_code` (not
    the airport code) to `search_flights` for the widest choice of fares.

    Pass either `near` (resolved against the city and airport datasets) or an
    explicit `latitude`/`longitude` pair.

    Args:
        near: Place name or IATA code to search around (e.g. "Pattaya", "UTP").
        latitude: Latitude in degrees, -90 to 90. Overrides `near`.
        longitude: Longitude in degrees, -180 to 180. Overrides `near`.
        limit: Max airports to return (1-50, default 5).
        max_distance_km: Ignore airports further away than this. Optional.
        flightable_only: Skip airports with no scheduled service (default True).
        locale: 2-letter locale for names. Defaults to the server's locale.

    Returns:
        Dict with "status", "origin" (what the query resolved to), "total",
        "returned", "truncated" and "data" (airports with distance_km, nearest
        first).
    """
    locale = validation.two_letter_code(locale, "locale", settings.aviasales_locale)
    airports = await _dataset(_dataset_path("airports", locale))

    origin_info: dict[str, Any]
    if latitude is not None or longitude is not None:
        if latitude is None or longitude is None:
            raise validation.InvalidArgumentError(
                "latitude and longitude must be given together, or use near=<place>."
            )
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise validation.InvalidArgumentError(
                f"latitude must be -90..90 and longitude -180..180, got {latitude}, {longitude}."
            )
        point = (float(latitude), float(longitude))
        origin_info = {"matched": "coordinates", "coordinates": {"lat": point[0], "lon": point[1]}}
    elif near:
        cities = await _dataset(_dataset_path("cities", locale))
        resolved = _resolve_place(near, cities, airports)
        if resolved is None:
            return _error(
                f'Could not resolve "{near}" to a place with coordinates.',
                "Try lookup_cities to find the exact name or IATA code, "
                "or pass latitude/longitude directly.",
            )
        point, origin_info = resolved
        origin_info["query"] = near
    else:
        raise validation.InvalidArgumentError(
            'find_nearest_airports needs near="<place>" or latitude+longitude.'
        )

    scored = []
    for airport in airports:
        if flightable_only and not _is_flightable(airport):
            continue
        coords = _coordinates(airport)
        if coords is None:
            continue
        distance = _haversine(point[0], point[1], coords[0], coords[1])
        if max_distance_km is not None and distance > max_distance_km:
            continue
        scored.append((distance, airport))

    scored.sort(key=lambda pair: pair[0])
    page = [
        {**_slim(airport), "distance_km": round(distance, 1)}
        for distance, airport in scored[:limit]
    ]
    payload: dict[str, Any] = {
        "status": "ok",
        "origin": origin_info,
        "total": len(scored),
        "returned": len(page),
        "truncated": len(scored) > len(page),
        "data": page,
    }
    if not page:
        payload["hint"] = (
            "No airport matched. Widen or drop max_distance_km, "
            "or set flightable_only=false."
        )
    return payload
