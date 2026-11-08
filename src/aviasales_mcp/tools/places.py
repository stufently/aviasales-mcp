"""Small, server-side searches of public Travelpayouts place autocomplete."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from aviasales_mcp import validation
from aviasales_mcp.api.client import ApiError, get_places
from aviasales_mcp.config import settings
from aviasales_mcp.tools.reference import _error
from aviasales_mcp.tools.responses import guard

_PLACE_FIELDS = (
    "type", "code", "name", "city_code", "city_name", "country_code", "country_name",
    "state_code", "main_airport_name", "coordinates",
)
_PLACES_HINT = (
    "Try a shorter term or a different locale, or use lookup_cities to search the city dataset."
)


@guard(_error, hint=_PLACES_HINT)
async def find_places(
    term: str,
    types: list[Literal["city", "airport", "country"]] | None = None,
    locale: str | None = None,
    limit: Annotated[int, Field(ge=1, le=20)] = 10,
) -> dict:
    """Find cities, airports and countries by name with public autocomplete.

    Use when a city, airport or country name needs an IATA code: this is faster
    and lighter than downloading the dataset with `lookup_cities`. For the
    closest airport to a town use `find_nearest_airports` instead. Results keep
    upstream relevance order; autocomplete returns at most 20 matches.

    Args:
        term: Place name or code prefix, at least 2 characters after trimming.
        types: Place types: city, airport, country. Defaults to city and airport;
            duplicates are removed while preserving order.
        locale: 2-letter language for names. Defaults to the server's locale.
        limit: Maximum results to return (1-20, default 10).

    Returns:
        Dict with status, term, locale, types, total (upstream row count),
        returned, truncated and data (place objects with codes and names).
        Empty results and errors include a hint naming the next step.
    """
    term = term.strip()
    if len(term) < 2:
        raise validation.InvalidArgumentError(
            "term must contain at least 2 characters after trimming.",
            "Send at least 2 characters of a city, airport or country name as term; "
            "or use lookup_cities with a known IATA code.",
        )
    requested_types = ["city", "airport"] if types is None else types
    if any(kind not in ("city", "airport", "country") for kind in requested_types):
        raise validation.InvalidArgumentError(
            "types must contain only city, airport or country.",
            "Set types to a list of city, airport and/or country, or omit it "
            "to search cities and airports with find_places.",
        )
    types = list(dict.fromkeys(requested_types))
    locale = validation.two_letter_code(locale, "locale", settings.aviasales_locale)
    rows = await get_places({"term": term, "locale": locale, "types[]": types})
    if not isinstance(rows, list):
        raise ApiError("Place autocomplete returned a non-list response")
    data = [
        {key: row[key] for key in _PLACE_FIELDS if key in row}
        for row in rows if isinstance(row, dict)
    ][:max(1, min(limit, 20))]
    payload: dict[str, Any] = {
        "status": "ok", "term": term, "locale": locale, "types": types,
        "total": len(rows), "returned": len(data), "truncated": len(data) < len(rows),
        "data": data,
    }
    if not data:
        payload["hint"] = _PLACES_HINT
    return payload
