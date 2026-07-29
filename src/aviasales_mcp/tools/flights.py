"""MCP tools for flight price search via Travelpayouts API v3."""

from __future__ import annotations

import re
import statistics
from datetime import datetime
from typing import Annotated, Any, Literal
from urllib.parse import parse_qsl, urlencode

from pydantic import Field

from aviasales_mcp import validation
from aviasales_mcp.api.client import get
from aviasales_mcp.config import settings
from aviasales_mcp.tools.responses import guard

# Trip class letters used in Aviasales search-link passenger blocks.
_TRIP_CLASS_LETTERS = {"economy": "", "comfort": "w", "business": "c", "first": "f"}
_CLASS_LETTERS = "".join(letter for letter in _TRIP_CLASS_LETTERS.values() if letter)
TRIP_CLASSES = tuple(_TRIP_CLASS_LETTERS)

# Deep-link path: /search/ + ORIGIN + DDMM + DEST [+ DDMM] + passenger block.
_SEARCH_LINK_RE = re.compile(
    rf"^(?P<route>/search/[A-Z]{{3}}\d{{4}}[A-Z]{{3}}(?:\d{{4}})?)"
    rf"(?:[{_CLASS_LETTERS}]?\d{{1,3}})(?P<query>\?.*)?$"
)

_PRICE_NOTE = (
    "Prices are per adult in economy (cached). "
    "booking_link opens the search for the full party with the actual total."
)

# Durations arrive as bare integers and timestamps carry the airport's own
# offset; without this the model has to guess at both.
_FIELD_NOTE = (
    "All duration fields are in minutes. departure_at/return_at are local time "
    "at the respective airport."
)

_NO_RESULTS_HINT = (
    "Empty result means the price cache has nothing for this query, not that the route "
    "does not exist. Try a whole month (departure_at as YYYY-MM), drop direct=true, widen "
    "or remove the depart_after/depart_before window, or confirm the codes with lookup_cities."
)

_API_ERROR_HINT = "The Travelpayouts API call failed. Retry, or check the codes with lookup_cities."

_MAX_API_LIMIT = 100


def _error_response(message: str, hint: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "error", "error": message, "data": []}
    if hint:
        payload["hint"] = hint
    return payload


def _validate_trip_class(trip_class: str) -> str:
    """Validate a trip class against the ones Aviasales deep links can express."""
    return validation.one_of(trip_class, "trip_class", TRIP_CLASSES)


def _price_note(trip_class: str) -> str:
    """Explain what the cached prices do and do not cover for this trip class."""
    if trip_class == "economy":
        return _PRICE_NOTE
    return (
        f"{_PRICE_NOTE} The cache holds economy fares only, so these prices are NOT "
        f"{trip_class}-class prices — the link opens {trip_class} and will show a higher total."
    )


def _clamp_party(adults: int, children: int, infants: int) -> tuple[int, int, int]:
    """Clamp party sizes to a combination Aviasales search links actually accept.

    Beyond the per-category caps there are two combination rules: seated
    passengers (adults + children) top out at 9, and there cannot be more lap
    infants than adults to hold them. A link that breaks either rule is silently
    reset to a single passenger by Aviasales — verified by rendering
    ``/search/MOW2509BKK92`` (9 adults + 2 children), which comes back as
    "1 пассажир" — so trimming here beats handing out a link that lies.
    """
    adults = max(1, min(adults, 9))
    children = max(0, min(children, 8, 9 - adults))
    infants = max(0, min(infants, 8, adults))
    return adults, children, infants


def _passenger_block(adults: int, children: int, infants: int, trip_class: str) -> str:
    """Encode passengers/class as an Aviasales search-link block (e.g. "2", "c21", "101")."""
    letter = _TRIP_CLASS_LETTERS.get(trip_class.strip().lower(), "")
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
        # Set rather than append: a fragment that already carries a marker would
        # otherwise end up with two, and which one counts is anyone's guess.
        path, _, query = link_fragment.partition("?")
        params = [(k, v) for k, v in parse_qsl(query, keep_blank_values=True) if k != "marker"]
        params.append(("marker", partner_id))
        link_fragment = f"{path}?{urlencode(params)}"
    return f"https://www.aviasales.ru{link_fragment}"


def _route_booking_link(
    origin: str,
    destination: str,
    depart: str,
    ret: str,
    passenger_block: str = "1",
) -> str:
    """Build an Aviasales deep link from a route and its dates.

    The v2-shaped endpoints (latest prices, the week/month matrices, the nearby
    matrix) return no ``link`` at all, so every one of their results used to be
    unclickable — and unattributed. The deep-link path is deterministic:
    ``/search/`` + ORIGIN + DDMM + DEST [+ DDMM] + passenger block.
    """
    if not origin or not destination or not depart:
        return ""
    try:
        depart_ddmm = f"{datetime.fromisoformat(depart[:10]):%d%m}"
    except ValueError:
        return ""
    fragment = f"/search/{origin.upper()}{depart_ddmm}{destination.upper()}"
    if ret:
        try:
            fragment += f"{datetime.fromisoformat(ret[:10]):%d%m}"
        except ValueError:
            pass
    return _build_booking_link(f"{fragment}{passenger_block}", passenger_block)


def _with_route_link(ticket: dict, passenger_block: str = "1") -> dict:
    """Fill in a missing booking link from the ticket's own route and dates."""
    if not ticket.get("booking_link"):
        ticket["booking_link"] = _route_booking_link(
            ticket.get("origin", ""),
            ticket.get("destination", ""),
            ticket.get("departure_at", ""),
            ticket.get("return_at", ""),
            passenger_block,
        )
    return ticket


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


def _format_v2_ticket(t: dict, passenger_block: str = "1") -> dict:
    """Format a v2-shaped ticket (latest prices, week/month and nearby matrices).

    These rows name the *agency* in `gate` — live values are "Kupi.com",
    "Aviakassa", "Biletix" — which is not an airline, and they carry no airline
    field at all. Reporting `gate` as `airline` mislabelled every result.
    """
    origin = t.get("origin", "")
    destination = t.get("destination", "")
    depart = t.get("depart_date", "")
    ret = t.get("return_date", "")
    return {
        "origin": origin,
        "destination": destination,
        "price": t.get("value"),
        "agency": t.get("gate", ""),
        "airline": None,
        "flight_number": None,
        "departure_at": depart,
        "return_at": ret,
        "transfers": t.get("number_of_changes", 0),
        "return_transfers": None,
        "duration_total": t.get("duration"),
        "duration_to": None,
        "duration_back": None,
        "layover_minutes": None,
        "distance_km": t.get("distance"),
        "found_at": t.get("found_at", ""),
        "expires_at": "",
        "booking_link": _route_booking_link(origin, destination, depart, ret, passenger_block),
    }


def _format_price_range_ticket(t: dict, passenger_block: str = "1") -> dict:
    """Format a search_by_price_range row, which names cities rather than codes only."""
    return {
        "origin": t.get("origin_code", ""),
        "origin_name": t.get("origin_name", ""),
        "origin_airport": t.get("origin_airport", ""),
        "destination": t.get("destination_code", ""),
        "destination_name": t.get("destination_name", ""),
        "destination_airport": t.get("destination_airport", ""),
        "price": t.get("price"),
        "departure_at": t.get("departure_at", ""),
        "return_at": t.get("return_at", ""),
        "transfers": t.get("transfers", 0),
        "duration_total": t.get("duration"),
        "booking_link": _build_booking_link(t.get("link", ""), passenger_block),
    }


def _price_summary(tickets: list[dict]) -> dict[str, Any] | None:
    """Cheapest/median/priciest across the returned tickets.

    Without a baseline the model cannot tell whether a quoted fare is a good
    deal, and its only recourse is another search.
    """
    prices = [t["price"] for t in tickets if isinstance(t.get("price"), int | float)]
    if not prices:
        return None
    return {
        "min": min(prices),
        "median": round(statistics.median(prices), 2),
        "max": max(prices),
        "count": len(prices),
    }


def _departure_minutes(ticket: dict) -> int | None:
    """Minutes since midnight of a ticket's departure, in local airport time."""
    raw = ticket.get("departure_at") or ""
    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    return parsed.hour * 60 + parsed.minute


def _in_window(minutes: int, after: int | None, before: int | None) -> bool:
    """Whether a time of day falls inside the requested window.

    ``after > before`` is read as a window that wraps midnight, which is how a
    request like "red-eyes only, after 22:00 and before 06:00" has to behave.
    """
    if after is not None and before is not None:
        if after <= before:
            return after <= minutes <= before
        return minutes >= after or minutes <= before
    if after is not None:
        return minutes >= after
    if before is not None:
        return minutes <= before
    return True


def _apply_time_filter(
    tickets: list[dict], after: int | None, before: int | None
) -> list[dict]:
    """Keep tickets departing inside the window; drop ones with no usable time."""
    if after is None and before is None:
        return tickets
    kept = []
    for ticket in tickets:
        minutes = _departure_minutes(ticket)
        if minutes is not None and _in_window(minutes, after, before):
            kept.append(ticket)
    return kept


@guard(_error_response, hint=_API_ERROR_HINT)
async def search_flights(
    origin: str,
    destination: str,
    departure_at: str | None = None,
    return_at: str | None = None,
    direct: bool = False,
    limit: Annotated[int, Field(ge=1, le=100)] = 10,
    currency: str | None = None,
    market: str | None = None,
    one_way: bool = False,
    adults: Annotated[int, Field(ge=1, le=9)] = 1,
    children: Annotated[int, Field(ge=0, le=8)] = 0,
    infants: Annotated[int, Field(ge=0, le=8)] = 0,
    trip_class: Literal["economy", "comfort", "business", "first"] = "economy",
    depart_after: str | None = None,
    depart_before: str | None = None,
) -> dict:
    """Search flight prices between two cities.

    Both codes must be IATA — call `lookup_cities` first if you only have a city
    name. For the cheapest date across a whole month use `get_prices_calendar`;
    for nearby airports use `get_alternative_directions`. A multi-city trip needs
    one call per leg.

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
        departure_at: Departure date or month (YYYY-MM-DD or YYYY-MM). Optional;
            a month searches every day in it.
        return_at: Return date or month (YYYY-MM-DD or YYYY-MM). Optional.
        direct: If True, show only non-stop flights.
        limit: Max number of results (1-100, default 10).
        currency: Price currency code (3 letters, e.g. "rub", "usd"). Defaults to
            the server's configured currency.
        market: 2-letter market whose price cache to read (e.g. "us", "ru", "th").
            The same route in the same currency is priced differently per market,
            so set this to the traveller's country. Defaults to the server's
            configured market.
        one_way: If True, search one-way tickets only.
        adults: Number of adult passengers, 1-9 (default 1).
        children: Number of children 2-11 years, 0-8 (default 0). Adults plus
            children cannot exceed 9; the excess is trimmed.
        infants: Number of infants under 2, 0-8 (default 0). Cannot exceed the
            number of adults; the excess is trimmed.
        trip_class: "economy", "comfort", "business" or "first" (default "economy").
        depart_after: Keep only flights departing at or after this local time
            ("HH:MM", 24-hour). Optional.
        depart_before: Keep only flights departing at or before this local time
            ("HH:MM", 24-hour). Optional. Combined with depart_after and set
            earlier than it, the window wraps midnight (e.g. 22:00-06:00).

    Returns:
        Dict with "status", "currency", "passengers", "price_note",
        "price_summary" (min/median/max across the results) and "data"
        (list of ticket objects with booking links for the whole party).
    """
    origin = validation.iata_code(origin, "origin")
    destination = validation.iata_code(destination, "destination")
    departure_at = validation.date_or_month(departure_at, "departure_at")
    return_at = validation.date_or_month(return_at, "return_at")
    currency = validation.currency_code(currency, settings.aviasales_default_currency)
    market = validation.two_letter_code(market, "market", settings.aviasales_market)
    trip_class = _validate_trip_class(trip_class)
    after = validation.time_of_day(depart_after, "depart_after")
    before = validation.time_of_day(depart_before, "depart_before")

    adults, children, infants = _clamp_party(adults, children, infants)
    block = _passenger_block(adults, children, infants, trip_class)

    limit = max(1, min(limit, _MAX_API_LIMIT))
    filtering = after is not None or before is not None
    # The window is applied to what the API returned, so when one is set ask for
    # everything available: a small `limit` would otherwise decide the answer
    # before the filter ran and report "nothing departs then" from a sample.
    api_limit = _MAX_API_LIMIT if filtering else limit

    resp = await get(
        "/aviasales/v3/prices_for_dates",
        origin=origin,
        destination=destination,
        departure_at=departure_at,
        return_at=return_at,
        direct=str(direct).lower() if direct else None,
        limit=api_limit,
        currency=currency,
        market=market,
        one_way=str(one_way).lower() if one_way else None,
    )
    tickets = [_format_v3_ticket(t, block) for t in resp.get("data", [])]
    considered = len(tickets)
    if filtering:
        tickets = _apply_time_filter(tickets, after, before)
    matched = len(tickets)
    tickets = tickets[:limit]

    result: dict[str, Any] = {
        "status": "ok",
        "currency": resp.get("currency", currency),
        "passengers": {"adults": adults, "children": children, "infants": infants},
        "trip_class": trip_class,
        "price_note": _price_note(trip_class),
        "field_note": _FIELD_NOTE,
        "price_summary": _price_summary(tickets),
        "data": tickets,
    }
    if filtering:
        result["time_filter"] = {
            "depart_after": depart_after,
            "depart_before": depart_before,
            "considered": considered,
            "matched": matched,
        }
    if not tickets:
        result["hint"] = _NO_RESULTS_HINT
    return result


@guard(_error_response, hint=_API_ERROR_HINT)
async def get_prices_calendar(
    origin: str,
    destination: str,
    departure_at: str | None = None,
    return_at: str | None = None,
    currency: str | None = None,
    market: str | None = None,
    group_by: Literal["departure_at", "month"] = "departure_at",
    adults: Annotated[int, Field(ge=1, le=9)] = 1,
    children: Annotated[int, Field(ge=0, le=8)] = 0,
    infants: Annotated[int, Field(ge=0, le=8)] = 0,
    trip_class: Literal["economy", "comfort", "business", "first"] = "economy",
) -> dict:
    """Get grouped (calendar) prices for a route — the cheapest day or month to fly.

    Use this instead of `search_flights` when the question is "when is it
    cheapest" rather than "what is available on this date". Codes are IATA; use
    `lookup_cities` to resolve a name first.

    Prices are per adult (cached); passenger parameters are encoded into each
    booking_link.

    Args:
        origin: Origin IATA code.
        destination: Destination IATA code.
        departure_at: Departure month (YYYY-MM). Optional.
        return_at: Return month (YYYY-MM). Optional.
        currency: Price currency (3 letters). Defaults to the server's currency.
        market: 2-letter market whose price cache to read (e.g. "us", "ru").
            Defaults to the server's configured market.
        group_by: Group results by "departure_at" or "month" (default "departure_at").
        adults: Number of adult passengers, 1-9 (default 1).
        children: Number of children 2-11 years, 0-8 (default 0). Adults plus
            children cannot exceed 9; the excess is trimmed.
        infants: Number of infants under 2, 0-8 (default 0). Cannot exceed the
            number of adults; the excess is trimmed.
        trip_class: "economy", "comfort", "business" or "first" (default "economy").

    Returns:
        Dict with "status", "currency", "price_summary" and "data" — grouped
        price data keyed by date or month.
    """
    origin = validation.iata_code(origin, "origin")
    destination = validation.iata_code(destination, "destination")
    departure_at = validation.date_or_month(departure_at, "departure_at")
    return_at = validation.date_or_month(return_at, "return_at")
    currency = validation.currency_code(currency, settings.aviasales_default_currency)
    market = validation.two_letter_code(market, "market", settings.aviasales_market)
    group_by = validation.one_of(group_by, "group_by", ("departure_at", "month"))
    trip_class = _validate_trip_class(trip_class)

    adults, children, infants = _clamp_party(adults, children, infants)
    block = _passenger_block(adults, children, infants, trip_class)

    resp = await get(
        "/aviasales/v3/grouped_prices",
        origin=origin,
        destination=destination,
        departure_at=departure_at,
        return_at=return_at,
        currency=currency,
        market=market,
        group_by=group_by,
    )
    raw = resp.get("data", {})
    result = {}
    for key, val in raw.items():
        if isinstance(val, dict):
            result[key] = _format_v3_ticket(val, block)
        else:
            result[key] = val

    payload: dict[str, Any] = {
        "status": "ok",
        "currency": resp.get("currency", currency),
        "passengers": {"adults": adults, "children": children, "infants": infants},
        "trip_class": trip_class,
        "price_note": _price_note(trip_class),
        "field_note": _FIELD_NOTE,
        "price_summary": _price_summary([v for v in result.values() if isinstance(v, dict)]),
        "data": result,
    }
    if not result:
        payload["hint"] = _NO_RESULTS_HINT
    return payload


@guard(_error_response, hint=_API_ERROR_HINT)
async def get_latest_prices(
    origin: str | None = None,
    destination: str | None = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
    currency: str | None = None,
    market: str | None = None,
    one_way: bool = False,
    adults: Annotated[int, Field(ge=1, le=9)] = 1,
    children: Annotated[int, Field(ge=0, le=8)] = 0,
    infants: Annotated[int, Field(ge=0, le=8)] = 0,
    trip_class: Literal["economy", "comfort", "business", "first"] = "economy",
) -> dict:
    """Get the latest (most recently found) flight prices.

    This is a firehose of what other users just searched, not a search for a
    specific trip — for that use `search_flights`. Prices are per adult (cached);
    passenger parameters are encoded into each booking_link.

    These rows come from the older v2 shape: they name the selling `agency`
    rather than an airline, carry no flight number, and their booking_link is
    reconstructed from the route and dates.

    Args:
        origin: Origin IATA code. Optional.
        destination: Destination IATA code. Optional.
        limit: Max results (1-100, default 20).
        currency: Price currency (3 letters). Defaults to the server's currency.
        market: 2-letter market whose price cache to read. Defaults to the
            server's configured market.
        one_way: One-way tickets only.
        adults: Number of adult passengers, 1-9 (default 1).
        children: Number of children 2-11 years, 0-8 (default 0). Adults plus
            children cannot exceed 9; the excess is trimmed.
        infants: Number of infants under 2, 0-8 (default 0). Cannot exceed the
            number of adults; the excess is trimmed.
        trip_class: "economy", "comfort", "business" or "first" (default "economy").

    Returns:
        Dict with "status", "currency", "price_summary" and "data" (list of tickets).
    """
    origin = validation.iata_code(origin, "origin", required=False)
    destination = validation.iata_code(destination, "destination", required=False)
    currency = validation.currency_code(currency, settings.aviasales_default_currency)
    market = validation.two_letter_code(market, "market", settings.aviasales_market)
    trip_class = _validate_trip_class(trip_class)

    adults, children, infants = _clamp_party(adults, children, infants)
    block = _passenger_block(adults, children, infants, trip_class)

    resp = await get(
        "/aviasales/v3/get_latest_prices",
        origin=origin,
        destination=destination,
        limit=max(1, min(limit, _MAX_API_LIMIT)),
        currency=currency,
        market=market,
        one_way=str(one_way).lower() if one_way else None,
    )
    # Despite the v3 path this endpoint answers in the v2 shape (value/gate/
    # depart_date). Running it through the v3 formatter returned price=None,
    # airline="" and departure_at="" for every row.
    tickets = [_format_v2_ticket(t, block) for t in resp.get("data", [])]
    payload: dict[str, Any] = {
        "status": "ok",
        "currency": resp.get("currency", currency),
        "passengers": {"adults": adults, "children": children, "infants": infants},
        "trip_class": trip_class,
        "price_note": _price_note(trip_class),
        "field_note": _FIELD_NOTE,
        "price_summary": _price_summary(tickets),
        "data": tickets,
    }
    if not tickets:
        payload["hint"] = _NO_RESULTS_HINT
    return payload


@guard(_error_response, hint=_API_ERROR_HINT)
async def get_popular_directions(
    destination: str,
    currency: str | None = None,
    locale: str | None = None,
) -> dict:
    """Get the cities people most often fly to a destination FROM.

    Direction matters: this answers "where do travellers reach BKK from, and for
    how much", keyed on the destination. For the opposite question — "where can I
    fly from Moscow" — use `get_city_directions`. For prices on a known route use
    `search_flights`.

    Args:
        destination: Destination IATA code (e.g. "BKK"). Required — the API
            rejects a request without it.
        currency: Price currency (3 letters). Defaults to the server's currency.
        locale: 2-letter locale for city names. Defaults to the server's locale.

    Returns:
        Dict with "status", "currency", "destination" (the resolved city) and
        "data" (origin cities with a sample price and dates).
    """
    destination = validation.iata_code(destination, "destination")
    currency = validation.currency_code(currency, settings.aviasales_default_currency)
    locale = validation.two_letter_code(locale, "locale", settings.aviasales_locale)

    resp = await get(
        "/aviasales/v3/get_popular_directions",
        destination=destination,
        currency=currency,
        locale=locale,
    )
    raw = resp.get("data") or {}
    origins = raw.get("origin", []) if isinstance(raw, dict) else []
    payload: dict[str, Any] = {
        "status": "ok",
        "currency": resp.get("currency", currency),
        "destination": raw.get("destination", {}) if isinstance(raw, dict) else {},
        "data": origins,
    }
    if not origins:
        payload["hint"] = _NO_RESULTS_HINT
    return payload


@guard(_error_response, hint=_API_ERROR_HINT)
async def get_city_directions(
    origin: str,
    currency: str | None = None,
) -> dict:
    """Get the cheapest destinations reachable FROM a city — "where can I fly from X".

    This is the inspiration search for an open-ended "somewhere warm, cheap,
    soon" question: one call returns many destinations with a real fare and
    dates. Narrow it down afterwards with `search_flights` or
    `get_prices_calendar`.

    Args:
        origin: Origin city IATA code (e.g. "MOW"). Use `lookup_cities` to
            resolve a city name first.
        currency: Price currency (3 letters). Defaults to the server's currency.

    Returns:
        Dict with "status", "currency" and "data" — destination code to cheapest
        ticket, each with a booking link.
    """
    origin = validation.iata_code(origin, "origin")
    currency = validation.currency_code(currency, settings.aviasales_default_currency)

    resp = await get("/v1/city-directions", origin=origin, currency=currency)
    raw = resp.get("data", {})
    # This endpoint returns no `link`, so the deep link has to be rebuilt from
    # the route and dates or every result would be unclickable.
    data = {
        key: _with_route_link(_format_v3_ticket(val)) if isinstance(val, dict) else val
        for key, val in raw.items()
    }
    payload: dict[str, Any] = {
        "status": "ok",
        "currency": resp.get("currency", currency),
        "price_note": _PRICE_NOTE,
        "field_note": _FIELD_NOTE,
        "price_summary": _price_summary([v for v in data.values() if isinstance(v, dict)]),
        "data": data,
    }
    if not data:
        payload["hint"] = _NO_RESULTS_HINT
    return payload


@guard(_error_response, hint=_API_ERROR_HINT)
async def get_flexible_date_prices(
    origin: str,
    destination: str,
    depart_date: str,
    return_date: str | None = None,
    currency: str | None = None,
    market: str | None = None,
    adults: Annotated[int, Field(ge=1, le=9)] = 1,
    children: Annotated[int, Field(ge=0, le=8)] = 0,
    infants: Annotated[int, Field(ge=0, le=8)] = 0,
    trip_class: Literal["economy", "comfort", "business", "first"] = "economy",
) -> dict:
    """Compare prices for the days around your dates — "can I save by shifting a day?".

    Covers roughly a week's window around both the outbound and the return date,
    which is the question `search_flights` (one exact date) and
    `get_prices_calendar` (a whole month, departures only) both miss.

    Args:
        origin: Origin IATA code.
        destination: Destination IATA code.
        depart_date: Intended departure date (YYYY-MM-DD). Required.
        return_date: Intended return date (YYYY-MM-DD). Omit for one-way.
        currency: Price currency (3 letters). Defaults to the server's currency.
        market: 2-letter market whose price cache to read. Defaults to the
            server's configured market.
        adults: Number of adult passengers, 1-9 (default 1).
        children: Number of children 2-11 years, 0-8 (default 0).
        infants: Number of infants under 2, 0-8 (default 0).
        trip_class: "economy", "comfort", "business" or "first" (default "economy").

    Returns:
        Dict with "status", "currency", "price_summary" and "data" — one entry
        per date combination, cheapest first.
    """
    origin = validation.iata_code(origin, "origin")
    destination = validation.iata_code(destination, "destination")
    # The matrix takes full dates only; a month is a 400 from the API.
    depart_date = validation.full_date(depart_date, "depart_date", required=True)
    return_date = validation.full_date(return_date, "return_date")
    currency = validation.currency_code(currency, settings.aviasales_default_currency)
    market = validation.two_letter_code(market, "market", settings.aviasales_market)
    trip_class = _validate_trip_class(trip_class)

    adults, children, infants = _clamp_party(adults, children, infants)
    block = _passenger_block(adults, children, infants, trip_class)

    resp = await get(
        "/v2/prices/week-matrix",
        origin=origin,
        destination=destination,
        depart_date=depart_date,
        return_date=return_date,
        currency=currency,
        market=market,
    )
    tickets = [_format_v2_ticket(t, block) for t in resp.get("data", [])]
    tickets.sort(key=lambda t: (t["price"] is None, t["price"]))
    payload: dict[str, Any] = {
        "status": "ok",
        "currency": resp.get("currency", currency),
        "passengers": {"adults": adults, "children": children, "infants": infants},
        "trip_class": trip_class,
        "price_note": _price_note(trip_class),
        "field_note": _FIELD_NOTE,
        "price_summary": _price_summary(tickets),
        "data": tickets,
    }
    if not tickets:
        payload["hint"] = _NO_RESULTS_HINT
    return payload


@guard(_error_response, hint=_API_ERROR_HINT)
async def search_by_price_range(
    origin: str,
    value_min: Annotated[int, Field(ge=0)],
    value_max: Annotated[int, Field(ge=0)],
    destination: str | None = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
    currency: str | None = None,
    market: str | None = None,
) -> dict:
    """Find flights whose price falls inside a budget — "anywhere under 30000 from Moscow".

    Leave `destination` unset to let the budget pick the destination; that is the
    query none of the other tools can answer. Prices are per adult in economy.

    There is deliberately no date argument: this endpoint ignores one (verified —
    passing a December date returns the same July and September fares), and each
    result carries its own `departure_at`. To search a specific period use
    `search_flights` or `get_prices_calendar`.

    Args:
        origin: Origin IATA code.
        value_min: Lowest acceptable price, in `currency`.
        value_max: Highest acceptable price, in `currency`.
        destination: Destination IATA code. Optional — omit to search anywhere.
        limit: Max results (1-100, default 20).
        currency: Price currency (3 letters). Defaults to the server's currency.
        market: 2-letter market whose price cache to read. Defaults to the
            server's configured market.

    Returns:
        Dict with "status", "currency", "price_summary" and "data" (tickets with
        both city codes, names and a booking link).
    """
    origin = validation.iata_code(origin, "origin")
    destination = validation.iata_code(destination, "destination", required=False)
    currency = validation.currency_code(currency, settings.aviasales_default_currency)
    market = validation.two_letter_code(market, "market", settings.aviasales_market)
    if value_min > value_max:
        raise validation.InvalidArgumentError(
            f"value_min ({value_min}) cannot exceed value_max ({value_max})."
        )

    resp = await get(
        "/aviasales/v3/search_by_price_range",
        origin=origin,
        destination=destination,
        value_min=value_min,
        value_max=value_max,
        limit=max(1, min(limit, _MAX_API_LIMIT)),
        currency=currency,
        market=market,
    )
    tickets = [_format_price_range_ticket(t) for t in resp.get("data", [])]
    payload: dict[str, Any] = {
        "status": "ok",
        "currency": resp.get("currency", currency),
        "price_note": _PRICE_NOTE,
        "field_note": _FIELD_NOTE,
        "price_summary": _price_summary(tickets),
        "data": tickets,
    }
    if not tickets:
        payload["hint"] = _NO_RESULTS_HINT
    return payload


@guard(_error_response, hint=_API_ERROR_HINT)
async def get_alternative_directions(
    origin: str,
    destination: str,
    departure_at: str | None = None,
    return_at: str | None = None,
    limit: Annotated[int, Field(ge=1, le=20)] = 10,
    currency: str | None = None,
    market: str | None = None,
) -> dict:
    """Get prices for alternative (nearby) airports/cities.

    Useful when the traveller is flexible about the exact airport. To find which
    airports are near a place in the first place, use `find_nearest_airports`.

    Args:
        origin: Origin IATA code.
        destination: Destination IATA code.
        departure_at: Departure date (YYYY-MM-DD or YYYY-MM). Optional.
        return_at: Return date (YYYY-MM-DD or YYYY-MM). Optional.
        limit: Max results (1-20, default 10).
        currency: Price currency (3 letters). Defaults to the server's currency.
        market: 2-letter market whose price cache to read. Defaults to the
            server's configured market.

    Returns:
        Dict with "status", "origins", "destinations" and "data" (prices for
        nearby airport combinations).
    """
    origin = validation.iata_code(origin, "origin")
    destination = validation.iata_code(destination, "destination")
    departure_at = validation.date_or_month(departure_at, "departure_at")
    return_at = validation.date_or_month(return_at, "return_at")
    currency = validation.currency_code(currency, settings.aviasales_default_currency)
    market = validation.two_letter_code(market, "market", settings.aviasales_market)

    resp = await get(
        "/v2/prices/nearest-places-matrix",
        origin=origin,
        destination=destination,
        depart_date=departure_at,
        return_date=return_at,
        limit=max(1, min(limit, 20)),
        currency=currency,
        market=market,
    )
    prices = resp.get("prices", [])
    data = [_format_v2_ticket(t) for t in prices] if isinstance(prices, list) else prices
    payload: dict[str, Any] = {
        "status": "ok",
        "origins": resp.get("origins", []),
        "destinations": resp.get("destinations", []),
        "field_note": _FIELD_NOTE,
        "data": data,
    }
    if not data:
        payload["hint"] = _NO_RESULTS_HINT
    return payload
