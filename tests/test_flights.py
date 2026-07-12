import httpx
import pytest
import respx

from aviasales_mcp.tools.flights import (
    _build_booking_link,
    _passenger_block,
    get_latest_prices,
    get_popular_directions,
    get_prices_calendar,
    search_flights,
)

API_BASE = "https://api.travelpayouts.com"


def _mock_prices_for_dates(**ticket_overrides):
    """Install a respx mock for prices_for_dates returning one ticket."""
    ticket = {
        "origin": "MOW",
        "destination": "LED",
        "price": 3500,
        "airline": "SU",
        "flight_number": "SU-100",
        "departure_at": "2026-04-10T10:00:00Z",
        "return_at": "2026-04-15T18:00:00Z",
        "transfers": 0,
        "return_transfers": 0,
        "duration": 185,
        "duration_to": 90,
        "duration_back": 95,
        "link": "/search/MOWLED1004",
        "expires_at": "2026-04-01T00:00:00Z",
    }
    ticket.update(ticket_overrides)
    respx.get(f"{API_BASE}/aviasales/v3/prices_for_dates").mock(
        return_value=httpx.Response(
            200,
            json={"success": True, "currency": "rub", "data": [ticket]},
        )
    )


def test_passenger_block_encoding():
    assert _passenger_block(1, 0, 0, "economy") == "1"
    assert _passenger_block(2, 0, 0, "economy") == "2"
    assert _passenger_block(2, 1, 0, "economy") == "21"
    assert _passenger_block(1, 0, 1, "economy") == "101"
    assert _passenger_block(3, 2, 1, "business") == "c321"
    assert _passenger_block(2, 1, 0, "first") == "f21"
    assert _passenger_block(1, 0, 1, "comfort") == "w101"


def test_booking_link_rewrites_passengers_round_trip():
    link = _build_booking_link("/search/MAD2807BCN26081?t=IB169&search_date=11052023", "2")
    assert "/search/MAD2807BCN26082?t=IB169" in link
    assert "marker=12345" in link


def test_booking_link_rewrites_passengers_one_way():
    link = _build_booking_link("/search/MOW1607IST1", "21")
    assert link.startswith("https://www.aviasales.ru/search/MOW1607IST21")


def test_booking_link_default_single_adult_unchanged():
    link = _build_booking_link("/search/MAD2807BCN26081?t=IB169")
    assert "/search/MAD2807BCN26081?t=IB169" in link


def test_booking_link_unrecognized_fragment_left_intact():
    link = _build_booking_link("/search/WEIRD-FORMAT", "2")
    assert "/search/WEIRD-FORMAT" in link


@respx.mock
@pytest.mark.asyncio
async def test_search_flights_success():
    _mock_prices_for_dates()

    result = await search_flights("MOW", "LED", departure_at="2026-04")
    assert result["currency"] == "rub"
    assert result["passengers"] == {"adults": 1, "children": 0, "infants": 0}
    assert len(result["data"]) == 1
    ticket = result["data"][0]
    assert ticket["origin"] == "MOW"
    assert ticket["destination"] == "LED"
    assert ticket["price"] == 3500
    assert ticket["duration_total"] == 185
    assert ticket["layover_minutes"] == 0
    assert "aviasales.ru" in ticket["booking_link"]
    assert "12345" in ticket["booking_link"]


@respx.mock
@pytest.mark.asyncio
async def test_search_flights_layover_minutes():
    # Real-world shape: 855 min door-to-door, 675 min in the air, 1 transfer.
    _mock_prices_for_dates(
        destination="BKK", duration=855, duration_to=675, duration_back=0, transfers=1
    )

    result = await search_flights("MOW", "BKK", one_way=True)
    ticket = result["data"][0]
    assert ticket["duration_total"] == 855
    assert ticket["layover_minutes"] == 180


@respx.mock
@pytest.mark.asyncio
async def test_search_flights_layover_none_when_duration_missing():
    _mock_prices_for_dates(duration=None)

    result = await search_flights("MOW", "LED")
    assert result["data"][0]["layover_minutes"] is None


@respx.mock
@pytest.mark.asyncio
async def test_search_flights_two_passengers_in_booking_link():
    _mock_prices_for_dates(link="/search/MOW1004LED15041?t=SU100")

    result = await search_flights("MOW", "LED", departure_at="2026-04", adults=2)
    assert result["passengers"]["adults"] == 2
    assert "/search/MOW1004LED15042?t=SU100" in result["data"][0]["booking_link"]


@respx.mock
@pytest.mark.asyncio
async def test_search_flights_api_error():
    respx.get(f"{API_BASE}/aviasales/v3/prices_for_dates").mock(
        return_value=httpx.Response(
            200,
            json={"success": False, "error": "Invalid params"},
        )
    )

    result = await search_flights("XXX", "YYY")
    assert "error" in result
    assert "Invalid params" in result["error"]


@respx.mock
@pytest.mark.asyncio
async def test_search_flights_rate_limit():
    respx.get(f"{API_BASE}/aviasales/v3/prices_for_dates").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "0"})
    )

    result = await search_flights("MOW", "LED")
    assert "error" in result
    assert "Rate limit" in result["error"]


@respx.mock
@pytest.mark.asyncio
async def test_get_prices_calendar_success():
    respx.get(f"{API_BASE}/aviasales/v3/grouped_prices").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "currency": "rub",
                "data": {
                    "2026-04-10": {
                        "origin": "MOW",
                        "destination": "LED",
                        "price": 2900,
                        "airline": "DP",
                        "departure_at": "2026-04-10",
                        "return_at": "",
                        "transfers": 0,
                        "link": "/search/MOWLED1004",
                    }
                },
            },
        )
    )

    result = await get_prices_calendar("MOW", "LED", departure_at="2026-04")
    assert result["currency"] == "rub"
    assert "2026-04-10" in result["data"]


@respx.mock
@pytest.mark.asyncio
async def test_get_latest_prices_success():
    respx.get(f"{API_BASE}/aviasales/v3/get_latest_prices").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "currency": "rub",
                "data": [
                    {
                        "origin": "MOW",
                        "destination": "IST",
                        "price": 15000,
                        "airline": "TK",
                        "departure_at": "2026-05-01",
                        "return_at": "2026-05-10",
                        "transfers": 0,
                        "link": "",
                    }
                ],
            },
        )
    )

    result = await get_latest_prices(origin="MOW", limit=5)
    assert len(result["data"]) == 1
    assert result["data"][0]["price"] == 15000


@respx.mock
@pytest.mark.asyncio
async def test_get_popular_directions_success():
    respx.get(f"{API_BASE}/aviasales/v3/get_popular_directions").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "currency": "rub",
                "data": {
                    "IST": {
                        "origin": "MOW",
                        "destination": "IST",
                        "price": 12000,
                        "transfers": 0,
                        "airline": "TK",
                        "departure_at": "2026-05-01",
                        "return_at": "2026-05-10",
                    }
                },
            },
        )
    )

    result = await get_popular_directions("MOW")
    assert "IST" in result["data"]
