import httpx
import pytest
import respx

from aviasales_mcp.tools.flights import (
    get_latest_prices,
    get_popular_directions,
    get_prices_calendar,
    search_flights,
)

API_BASE = "https://api.travelpayouts.com"


@respx.mock
@pytest.mark.asyncio
async def test_search_flights_success():
    respx.get(f"{API_BASE}/aviasales/v3/prices_for_dates").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "currency": "rub",
                "data": [
                    {
                        "origin": "MOW",
                        "destination": "LED",
                        "price": 3500,
                        "airline": "SU",
                        "flight_number": "SU-100",
                        "departure_at": "2026-04-10T10:00:00Z",
                        "return_at": "2026-04-15T18:00:00Z",
                        "transfers": 0,
                        "return_transfers": 0,
                        "duration_to": 90,
                        "duration_back": 95,
                        "link": "/search/MOWLED1004",
                        "expires_at": "2026-04-01T00:00:00Z",
                    }
                ],
            },
        )
    )

    result = await search_flights("MOW", "LED", departure_at="2026-04")
    assert result["currency"] == "rub"
    assert len(result["data"]) == 1
    ticket = result["data"][0]
    assert ticket["origin"] == "MOW"
    assert ticket["destination"] == "LED"
    assert ticket["price"] == 3500
    assert "aviasales.ru" in ticket["booking_link"]
    assert "12345" in ticket["booking_link"]


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
