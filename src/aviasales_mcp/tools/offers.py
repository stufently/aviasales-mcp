"""Airline promotional fares from the Travelpayouts Data API."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field

from aviasales_mcp import validation
from aviasales_mcp.api.client import get
from aviasales_mcp.config import settings
from aviasales_mcp.tools.flights import (
    _API_ERROR_HINT,
    _FIELD_NOTE,
    _build_booking_link,
    _clamp_party,
    _error_response,
    _passenger_block,
    _price_note,
    _price_summary,
    _validate_trip_class,
    _with_route_link,
)
from aviasales_mcp.tools.responses import guard

_OFFER_FIELDS = (
    "origin", "origin_name", "origin_airport", "destination", "destination_name",
    "destination_airport", "airline", "airline_title", "flight_number", "departure_at",
    "return_at", "duration", "price", "title", "mini_title",
)


def _format_offer(row: dict, block: str) -> dict:
    ticket = {key: row[key] for key in _OFFER_FIELDS if key in row}
    fragment = row.get("link", "")
    if (
        isinstance(fragment, str)
        and fragment.startswith("/")
        and fragment[1:2] not in ("/", "\\")
        and not fragment.startswith("/search/")
    ):
        fragment = f"/search{fragment}"
    ticket["booking_link"] = _build_booking_link(fragment, block)
    return _with_route_link(ticket, block)


@guard(_error_response, hint=_API_ERROR_HINT)
async def get_special_offers(
    origin: str,
    destination: str | None = None,
    airline: str | None = None,
    currency: str | None = None,
    market: str | None = None,
    locale: str | None = None,
    adults: Annotated[int, Field(ge=1, le=9)] = 1,
    children: Annotated[int, Field(ge=0, le=8)] = 0,
    infants: Annotated[int, Field(ge=0, le=8)] = 0,
    trip_class: Literal["economy", "comfort", "business", "first"] = "economy",
    limit: Annotated[int, Field(ge=1, le=100)] = 30,
) -> dict:
    """Get airline promotions and special fares departing from a city.

    Use when the user wants promotional or last-minute offers from a known
    origin, optionally by airline or destination. Prices are cached per adult
    in economy; the booking link selects the full party and requested cabin.
    For recent ordinary fares use `get_latest_prices`; for destination ideas
    use `get_city_directions`.

    Args:
        origin: Required 3-letter IATA origin code. Omitting it would let the
            API choose a city from the server's IP instead of the user's city.
        destination: Optional 3-letter IATA destination code.
        airline: Optional 2-character IATA airline code, such as SU or S7;
            resolve airline names with `lookup_airlines`.
        currency: 3-letter price currency. Defaults to the server's currency.
        market: 2-letter price-cache market. Defaults to the server's market.
        locale: 2-letter language for names. Defaults to the server's locale.
        adults: Adult passengers, 1-9 (default 1).
        children: Children 2-11 years, 0-8; adults plus children are trimmed to 9.
        infants: Infants under 2, 0-8; trimmed to the number of adults.
        trip_class: economy, comfort, business or first (default economy).
        limit: Maximum offers to return, 1-100 (default 30).

    Returns:
        Dict with status, currency, passengers, trip_class, price_note,
        field_note, price_summary across returned offers, total, returned and
        data (offers with booking_link). Empty results include a hint.
    """
    origin = validation.iata_code(origin, "origin")
    destination = validation.iata_code(destination, "destination", required=False)
    airline = validation.airline_code(airline)
    currency = validation.currency_code(currency, settings.aviasales_default_currency)
    market = validation.two_letter_code(market, "market", settings.aviasales_market)
    locale = validation.two_letter_code(locale, "locale", settings.aviasales_locale)
    trip_class = _validate_trip_class(trip_class)
    adults, children, infants = _clamp_party(adults, children, infants)
    block = _passenger_block(adults, children, infants, trip_class)

    resp = await get(
        "/aviasales/v3/get_special_offers", origin=origin, destination=destination,
        airline=airline, currency=currency, market=market, locale=locale,
    )
    if not isinstance(resp, dict):
        resp = {}
    raw = resp.get("data")
    rows = [row for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []
    tickets = [_format_offer(row, block) for row in rows[:max(1, min(limit, 100))]]
    payload: dict[str, Any] = {
        "status": "ok", "currency": resp.get("currency", currency),
        "passengers": {"adults": adults, "children": children, "infants": infants},
        "trip_class": trip_class, "price_note": _price_note(trip_class),
        "field_note": _FIELD_NOTE, "price_summary": _price_summary(tickets),
        "total": len(rows), "returned": len(tickets), "data": tickets,
    }
    if not tickets:
        payload["hint"] = (
            "No promotional fares are cached. Try omitting destination or airline, "
            "or use get_latest_prices for recent fares or get_city_directions for ideas."
        )
    return payload
