"""MCP tools for flight price search via Travelpayouts API v3."""

from __future__ import annotations

from aviasales_mcp.api.client import ApiError, RateLimitError, get
from aviasales_mcp.config import settings

AVIASALES_SEARCH_URL = "https://www.aviasales.ru/search"


def _build_booking_link(link_fragment: str) -> str:
    """Build a full Aviasales booking link from a deep-link fragment."""
    if not link_fragment:
        return ""
    partner_id = settings.aviasales_partner_id
    if partner_id:
        sep = "&" if "?" in link_fragment else "?"
        link_fragment = f"{link_fragment}{sep}marker={partner_id}"
    return f"https://www.aviasales.ru{link_fragment}"


def _format_v3_ticket(t: dict) -> dict:
    """Format a v3 API ticket response."""
    return {
        "origin": t.get("origin", ""),
        "destination": t.get("destination", ""),
        "price": t.get("price"),
        "airline": t.get("airline", ""),
        "flight_number": t.get("flight_number"),
        "departure_at": t.get("departure_at", ""),
        "return_at": t.get("return_at", ""),
        "transfers": t.get("transfers", 0),
        "return_transfers": t.get("return_transfers", 0),
        "duration_to": t.get("duration_to"),
        "duration_back": t.get("duration_back"),
        "expires_at": t.get("expires_at", ""),
        "booking_link": _build_booking_link(t.get("link", "")),
    }


def _format_v2_ticket(t: dict) -> dict:
    """Format a v2 API ticket response (different field names)."""
    return {
        "origin": t.get("origin", ""),
        "destination": t.get("destination", ""),
        "price": t.get("value"),
        "airline": t.get("gate", ""),
        "flight_number": None,
        "departure_at": t.get("depart_date", ""),
        "return_at": t.get("return_date", ""),
        "transfers": t.get("number_of_changes", 0),
        "return_transfers": 0,
        "duration_to": t.get("duration"),
        "duration_back": None,
        "expires_at": "",
        "booking_link": "",
    }


def _error_response(e: Exception) -> dict:
    return {"error": str(e), "data": []}


async def search_flights(
    origin: str,
    destination: str,
    departure_at: str | None = None,
    return_at: str | None = None,
    direct: bool = False,
    limit: int = 10,
    currency: str = "rub",
    sorting: str = "price",
    one_way: bool = False,
) -> dict:
    """Search flight prices between two cities.

    Args:
        origin: Origin city IATA code (e.g. "MOW", "LED").
        destination: Destination city IATA code (e.g. "IST", "BCN").
        departure_at: Departure date or month (YYYY-MM-DD or YYYY-MM). Optional.
        return_at: Return date or month (YYYY-MM-DD or YYYY-MM). Optional.
        direct: If True, show only non-stop flights.
        limit: Max number of results (1-100, default 10).
        currency: Price currency code (default "rub").
        sorting: Sort by "price" or "route" (default "price").
        one_way: If True, search one-way tickets only.

    Returns:
        Dict with "currency", "data" (list of ticket objects with booking links).
    """
    try:
        resp = await get(
            "/aviasales/v3/prices_for_dates",
            origin=origin,
            destination=destination,
            departure_at=departure_at,
            return_at=return_at,
            direct=str(direct).lower() if direct else None,
            limit=min(limit, 100),
            currency=currency,
            sorting=sorting,
            one_way=str(one_way).lower() if one_way else None,
            unique="false",
        )
        tickets = resp.get("data", [])
        return {
            "currency": resp.get("currency", currency),
            "data": [_format_v3_ticket(t) for t in tickets],
        }
    except (ApiError, RateLimitError) as e:
        return _error_response(e)


async def get_prices_calendar(
    origin: str,
    destination: str,
    departure_at: str | None = None,
    return_at: str | None = None,
    currency: str = "rub",
    group_by: str = "departure_at",
) -> dict:
    """Get grouped (calendar) prices for a route.

    Useful for finding the cheapest day/month to fly.

    Args:
        origin: Origin IATA code.
        destination: Destination IATA code.
        departure_at: Departure month (YYYY-MM). Optional.
        return_at: Return month (YYYY-MM). Optional.
        currency: Price currency (default "rub").
        group_by: Group results by "departure_at" or "month" (default "departure_at").

    Returns:
        Dict with grouped price data (keyed by date/month).
    """
    try:
        resp = await get(
            "/aviasales/v3/grouped_prices",
            origin=origin,
            destination=destination,
            departure_at=departure_at,
            return_at=return_at,
            currency=currency,
            group_by=group_by,
        )
        raw = resp.get("data", {})
        result = {}
        for key, val in raw.items():
            if isinstance(val, dict):
                result[key] = _format_v3_ticket(val)
            else:
                result[key] = val
        return {"currency": resp.get("currency", currency), "data": result}
    except (ApiError, RateLimitError) as e:
        return _error_response(e)


async def get_latest_prices(
    origin: str | None = None,
    destination: str | None = None,
    limit: int = 20,
    currency: str = "rub",
    one_way: bool = False,
) -> dict:
    """Get the latest (most recently found) flight prices.

    Args:
        origin: Origin IATA code. Optional.
        destination: Destination IATA code. Optional.
        limit: Max results (1-100, default 20).
        currency: Price currency (default "rub").
        one_way: One-way tickets only.

    Returns:
        Dict with "currency" and "data" (list of tickets).
    """
    try:
        resp = await get(
            "/aviasales/v3/get_latest_prices",
            origin=origin,
            destination=destination,
            limit=min(limit, 100),
            currency=currency,
            one_way=str(one_way).lower() if one_way else None,
        )
        tickets = resp.get("data", [])
        return {
            "currency": resp.get("currency", currency),
            "data": [_format_v3_ticket(t) for t in tickets],
        }
    except (ApiError, RateLimitError) as e:
        return _error_response(e)


async def get_popular_directions(
    origin: str | None = None,
    destination: str | None = None,
    currency: str = "rub",
    locale: str = "ru",
) -> dict:
    """Get popular flight directions from/to a city.

    The API supports both origin and destination — pass at least one.

    Args:
        origin: Origin IATA code (e.g. "MOW"). Optional.
        destination: Destination IATA code. Optional.
        currency: Price currency (default "rub").
        locale: Locale for city names (default "ru").

    Returns:
        Dict with popular direction data.
    """
    try:
        resp = await get(
            "/aviasales/v3/get_popular_directions",
            origin=origin,
            destination=destination,
            currency=currency,
            locale=locale,
        )
        return {
            "currency": resp.get("currency", currency),
            "data": resp.get("data", {}),
        }
    except (ApiError, RateLimitError) as e:
        return _error_response(e)


async def get_alternative_directions(
    origin: str,
    destination: str,
    departure_at: str | None = None,
    return_at: str | None = None,
    limit: int = 10,
    currency: str = "rub",
) -> dict:
    """Get prices for alternative (nearby) airports/cities.

    Useful when the user is flexible about exact origin/destination.

    Args:
        origin: Origin IATA code.
        destination: Destination IATA code.
        departure_at: Departure date (YYYY-MM-DD or YYYY-MM). Optional.
        return_at: Return date (YYYY-MM-DD or YYYY-MM). Optional.
        limit: Max results (1-20, default 10).
        currency: Price currency (default "rub").

    Returns:
        Dict with prices for nearby airport combinations.
    """
    try:
        resp = await get(
            "/v2/prices/nearest-places-matrix",
            origin=origin,
            destination=destination,
            depart_date=departure_at,
            return_date=return_at,
            limit=min(limit, 20),
            currency=currency,
        )
        prices = resp.get("prices", [])
        return {
            "origins": resp.get("origins", []),
            "destinations": resp.get("destinations", []),
            "data": [_format_v2_ticket(t) for t in prices] if isinstance(prices, list) else prices,
        }
    except (ApiError, RateLimitError) as e:
        return _error_response(e)
