import httpx
import pytest
import respx

from aviasales_mcp.api import client
from aviasales_mcp.tools import reference
from aviasales_mcp.tools.reference import (
    MAX_LIMIT,
    lookup_airlines,
    lookup_airports,
    lookup_cities,
    lookup_countries,
)

API_BASE = "https://api.travelpayouts.com"

AIRPORTS = [
    {
        "name_translations": {"en": "Heathrow", "ru": "Хитроу"},
        "cases": {"su": "Heathrow"},
        "code": "LHR",
        "name": "Heathrow",
        "city_code": "LON",
        "country_code": "GB",
        "coordinates": {"lat": 51.4706, "lon": -0.461941},
        "flightable": True,
    },
    {
        "name_translations": {"en": "Gatwick"},
        "code": "LGW",
        "name": "Gatwick",
        "city_code": "LON",
        "country_code": "GB",
        "flightable": True,
    },
    {
        "name_translations": {"en": "Suvarnabhumi"},
        "code": "BKK",
        "name": "Suvarnabhumi",
        "city_code": "BKK",
        "country_code": "TH",
        "flightable": True,
    },
]


def _mock_airports(payload=None):
    return respx.get(f"{API_BASE}/data/en/airports.json").mock(
        return_value=httpx.Response(200, json=AIRPORTS if payload is None else payload)
    )


@respx.mock
@pytest.mark.asyncio
async def test_lookup_airports_search_by_code():
    _mock_airports()

    result = await lookup_airports(search="LHR")
    assert result["total"] == 1
    assert result["returned"] == 1
    assert result["truncated"] is False
    assert result["data"][0]["code"] == "LHR"


@respx.mock
@pytest.mark.asyncio
async def test_lookup_airports_search_by_city_code():
    _mock_airports()

    result = await lookup_airports(search="lon")
    assert {a["code"] for a in result["data"]} == {"LHR", "LGW"}


@respx.mock
@pytest.mark.asyncio
async def test_lookup_airports_search_by_name_is_case_insensitive():
    _mock_airports()

    result = await lookup_airports(search="suvarna")
    assert result["total"] == 1
    assert result["data"][0]["code"] == "BKK"


@respx.mock
@pytest.mark.asyncio
async def test_lookup_airports_drops_bulk_translation_fields():
    _mock_airports()

    airport = (await lookup_airports(search="LHR"))["data"][0]
    assert "name_translations" not in airport
    assert "cases" not in airport
    # The useful fields survive.
    assert airport["name"] == "Heathrow"
    assert airport["country_code"] == "GB"
    assert airport["coordinates"]["lat"] == pytest.approx(51.4706)


@respx.mock
@pytest.mark.asyncio
async def test_lookup_airports_truncates_and_reports_total():
    _mock_airports()

    result = await lookup_airports(limit=2)
    assert result["total"] == 3
    assert result["returned"] == 2
    assert result["truncated"] is True


@respx.mock
@pytest.mark.asyncio
async def test_lookup_airports_clamps_limit():
    _mock_airports()

    assert (await lookup_airports(limit=0))["returned"] == 1
    assert (await lookup_airports(limit=-5))["returned"] == 1
    # Above MAX_LIMIT it simply returns everything that matched.
    assert (await lookup_airports(limit=MAX_LIMIT + 1_000))["returned"] == 3


@respx.mock
@pytest.mark.asyncio
async def test_lookup_airports_no_match_is_empty_not_an_error():
    _mock_airports()

    result = await lookup_airports(search="nowhere")
    assert result["total"] == 0
    assert result["data"] == []
    assert "error" not in result


@respx.mock
@pytest.mark.asyncio
async def test_dataset_is_cached_across_calls():
    route = _mock_airports()

    await lookup_airports(search="LHR")
    await lookup_airports(search="BKK")

    # 10k airports is ~2.7 MB — downloading it once per lookup is the whole point.
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_lookup_airports_api_error():
    respx.get(f"{API_BASE}/data/en/airports.json").mock(return_value=httpx.Response(401))

    result = await lookup_airports(search="LHR")
    assert "Unauthorized" in result["error"]
    assert result["data"] == []
    assert result["total"] == 0


@respx.mock
@pytest.mark.asyncio
async def test_persistent_rate_limit_returns_an_error_dict(monkeypatch):
    # RateLimitError is not an ApiError; if it escapes, the model sees a
    # protocol error instead of something it can act on.
    monkeypatch.setattr(client, "RETRY_BACKOFF", 0.0)
    respx.get(f"{API_BASE}/data/en/airports.json").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "0"})
    )

    result = await lookup_airports(search="LHR")
    assert "Rate limit" in result["error"]
    assert result["data"] == []


@respx.mock
@pytest.mark.asyncio
async def test_stale_cache_is_served_when_refresh_fails(monkeypatch):
    route = _mock_airports()
    await lookup_airports(search="LHR")

    # Expire the cache, then make the refresh fail.
    monkeypatch.setattr(reference, "CACHE_TTL_SECONDS", -1)
    route.mock(return_value=httpx.Response(500, text="down"))

    result = await lookup_airports(search="LHR")
    assert result["data"][0]["code"] == "LHR"
    assert "error" not in result


@respx.mock
@pytest.mark.asyncio
async def test_failure_without_a_cached_copy_is_an_error(monkeypatch):
    monkeypatch.setattr(client, "RETRY_BACKOFF", 0.0)
    respx.get(f"{API_BASE}/data/en/airports.json").mock(
        return_value=httpx.Response(500, text="down")
    )

    result = await lookup_airports(search="LHR")
    assert "HTTP 500" in result["error"]


@respx.mock
@pytest.mark.asyncio
async def test_lookup_airports_non_list_payload():
    _mock_airports(payload={"unexpected": "shape"})

    result = await lookup_airports(search="LHR")
    assert result["data"] == []
    assert result["total"] == 0


@respx.mock
@pytest.mark.asyncio
async def test_lookup_cities():
    respx.get(f"{API_BASE}/data/en/cities.json").mock(
        return_value=httpx.Response(
            200,
            json=[{"code": "BKK", "name": "Bangkok", "country_code": "TH"}],
        )
    )

    result = await lookup_cities(search="bangkok")
    assert result["data"][0]["code"] == "BKK"


@respx.mock
@pytest.mark.asyncio
async def test_lookup_airlines():
    respx.get(f"{API_BASE}/data/en/airlines.json").mock(
        return_value=httpx.Response(
            200,
            json=[{"code": "SU", "name": "Aeroflot", "is_lowcost": False}],
        )
    )

    result = await lookup_airlines(search="SU")
    assert result["data"][0]["name"] == "Aeroflot"


@respx.mock
@pytest.mark.asyncio
async def test_lookup_countries():
    respx.get(f"{API_BASE}/data/en/countries.json").mock(
        return_value=httpx.Response(
            200,
            json=[{"code": "TH", "name": "Thailand", "currency": "THB"}],
        )
    )

    result = await lookup_countries(search="thailand")
    assert result["data"][0]["currency"] == "THB"
