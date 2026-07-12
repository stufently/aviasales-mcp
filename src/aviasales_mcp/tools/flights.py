"""MCP tools for flight price search via Travelpayouts API v3."""

from __future__ import annotations

import re

from aviasales_mcp.api.client import ApiError, RateLimitError, get
from aviasales_mcp.config import settings

# Trip class letters used in Aviasales search-link passenger blocks.
_TRIP_CLASS_LETTERS = {"economy": "", "comfort": "w", "business": "c", "first": "f"}
_CLASS_LETTERS = "".join(letter for letter in _TRIP_CLASS_LETTERS.values() if letter)

# Deep-link path: /search/ + ORIGIN + DDMM + DEST [+ DDMM] + passenger block.
_SEARCH_LINK_RE = re.compile(
    rf"^(?P<route>/search/[A-Z]{{3}}\d{{4}}[A-Z]{{3}}(?:\d{{4}})?)"
    rf"(?:[{_CLASS_LETTERS}]?\d{{1,3}})(?P<query>\?.*)?$"
)

_PRICE_NOTE = (
    "Prices are per adult (economy, cached). "
    "booking_link opens the search for the full party with the actual total."
)


def _clamp_party(adults: int, children: int, infants: int) -> tuple[int, int, int]:
    """Clamp party sizes to what Aviasales search links support."""
    return max(1, min(adults, 9)), max(0, min(children, 8)), max(0, min(infants, 8))


def _passenger_block(adults: int, children: int, infants: int, trip_class: str) -> str:
    """Encode passengers/class as an Aviasales search-link block (e.g. "2", "c21", "101")."""
    letter = _TRIP_CLASS_LETTERS.get(trip_class.lower(), "")
    return letter + f"{adults}{children}{infants}".rstrip("0")


def _build_booking_link(link_fragment: str, passenger_block: str = "1") -> str:
    """Build a full Aviasales booking link from a deep-link fragment."""
    if not link_fragment:
        return ""
    m = _SEARCH_LINK_RE.match(link_fragment)
    if m:
        link_fragment = f"{m.group('route')}{passenger_block}{m.group('query') or ''}"
    partner_id = settings.aviasales_partner_id
    if partner_id:
        sep = "&" if "?" in link_fragment else "?"
        link_fragment = f"{link_fragment}{sep}marker={partner_id}"
    return f"https://www.aviasales.ru{link_fragment}"


def _layover_minutes(t: dict) -> int | None:
    """Total ground time between connecting flights, in minutes.

    The API reports `duration` as full door-to-door travel time and
    `duration_to`/`duration_back` as pure flight time per direction, so the
    difference is the combined layover time (both directions for round trips).
    """
    total = t.get("duration")
    flight_to = t.get("duration_to")
    if total is None or flight_to is None:
        return None
    layover = total - flight_to - (t.get("duration_back") or 0)
    return max(layover, 0)


def _format_v3_ticket(t: dict, passenger_block: str = "1") -> dict:
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
        "duration_total": t.get("duration"),
        "duration_to": t.get("duration_to"),
        "duration_back": t.get("duration_back"),
        "layover_minutes": _layover_minutes(t),
        "expires_at": t.get("expires_at", ""),
        "booking_link": _build_booking_link(t.get("link", ""), passenger_block),
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
        "duration_total": t.get("duration"),
        "duration_to": t.get("duration"),
        "duration_back": None,
        "layover_minutes": None,
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
    adults: int = 1,
    children: int = 0,
    infants: int = 0,
    trip_class: str = "economy",
) -> dict:
    """Search flight prices between two cities.

    Note on passengers: the price data comes from a cache of recent searches and
    is always PER ADULT in economy. The adults/children/infants/trip_class
    parameters are encoded into each ticket's booking_link, so the link opens
    Aviasales with the full party pre-filled and shows the real total price.

    Durations: each ticket reports duration_total (full door-to-door travel
    time), duration_to/duration_back (pure flight time per direction) and
    layover_minutes (combined ground time between connecting flights; 0 for
    direct flights). All values are in minutes.

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
        adults: Number of adult passengers, 1-9 (default 1).
        children: Number of children 2-11 years, 0-8 (default 0).
        infants: Number of infants under 2, 0-8 (default 0).
        trip_class: "economy", "comfort", "business" or "first" (default "economy").

    Returns:
        Dict with "currency", "passengers", "price_note" and "data"
        (list of ticket objects with booking links for the whole party).
    """
    adults, children, infants = _clamp_party(adults, children, infants)
    block = _passenger_block(adults, children, infants, trip_class)
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
            "passengers": {"adults": adults, "children": children, "infants": infants},
            "trip_class": trip_class,
            "price_note": _PRICE_NOTE,
            "data": [_format_v3_ticket(t, block) for t in tickets],
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
    adults: int = 1,
    children: int = 0,
    infants: int = 0,
    trip_class: str = "economy",
) -> dict:
    """Get grouped (calendar) prices for a route.

    Useful for finding the cheapest day/month to fly. Prices are per adult
    (cached); passenger parameters are encoded into each booking_link.

    Args:
        origin: Origin IATA code.
        destination: Destination IATA code.
        departure_at: Departure month (YYYY-MM). Optional.
        return_at: Return month (YYYY-MM). Optional.
        currency: Price currency (default "rub").
        group_by: Group results by "departure_at" or "month" (default "departure_at").
        adults: Number of adult passengers, 1-9 (default 1).
        children: Number of children 2-11 years, 0-8 (default 0).
        infants: Number of infants under 2, 0-8 (default 0).
        trip_class: "economy", "comfort", "business" or "first" (default "economy").

    Returns:
        Dict with grouped price data (keyed by date/month).
    """
    adults, children, infants = _clamp_party(adults, children, infants)
    block = _passenger_block(adults, children, infants, trip_class)
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
                result[key] = _format_v3_ticket(val, block)
            else:
                result[key] = val
        return {
            "currency": resp.get("currency", currency),
            "passengers": {"adults": adults, "children": children, "infants": infants},
            "trip_class": trip_class,
            "price_note": _PRICE_NOTE,
            "data": result,
        }
    except (ApiError, RateLimitError) as e:
        return _error_response(e)


async def get_latest_prices(
    origin: str | None = None,
    destination: str | None = None,
    limit: int = 20,
    currency: str = "rub",
    one_way: bool = False,
    adults: int = 1,
    children: int = 0,
    infants: int = 0,
    trip_class: str = "economy",
) -> dict:
    """Get the latest (most recently found) flight prices.

    Prices are per adult (cached); passenger parameters are encoded into
    each booking_link.

    Args:
        origin: Origin IATA code. Optional.
        destination: Destination IATA code. Optional.
        limit: Max results (1-100, default 20).
        currency: Price currency (default "rub").
        one_way: One-way tickets only.
        adults: Number of adult passengers, 1-9 (default 1).
        children: Number of children 2-11 years, 0-8 (default 0).
        infants: Number of infants under 2, 0-8 (default 0).
        trip_class: "economy", "comfort", "business" or "first" (default "economy").

    Returns:
        Dict with "currency" and "data" (list of tickets).
    """
    adults, children, infants = _clamp_party(adults, children, infants)
    block = _passenger_block(adults, children, infants, trip_class)
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
            "passengers": {"adults": adults, "children": children, "infants": infants},
            "trip_class": trip_class,
            "price_note": _PRICE_NOTE,
            "data": [_format_v3_ticket(t, block) for t in tickets],
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
