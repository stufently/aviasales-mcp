import httpx
import pytest
import respx

from aviasales_mcp.tools.reference import _haversine, find_nearest_airports

API_BASE = "https://api.travelpayouts.com"

# Real coordinates: Suvarnabhumi and U-Tapao are the two airports that serve
# Pattaya, and U-Tapao is much closer while being named after neither.
AIRPORTS = [
    {
        "code": "BKK",
        "name": "Suvarnabhumi Airport",
        "city_code": "BKK",
        "country_code": "TH",
        "coordinates": {"lat": 13.693062, "lon": 100.752045},
        "flightable": True,
    },
    {
        "code": "UTP",
        "name": "Utapao Airport",
        "city_code": "UTP",
        "country_code": "TH",
        "coordinates": {"lat": 12.683333, "lon": 101.01667},
        "flightable": True,
    },
    {
        "code": "DMK",
        "name": "Don Mueang Airport",
        "city_code": "BKK",
        "country_code": "TH",
        "coordinates": {"lat": 13.912583, "lon": 100.60675},
        "flightable": True,
    },
    {
        "code": "ZZZ",
        "name": "Disused Airstrip",
        "city_code": "UTP",
        "country_code": "TH",
        "coordinates": {"lat": 12.7, "lon": 101.0},
        "flightable": False,
    },
    {
        "code": "NOC",
        "name": "No Coordinates Field",
        "city_code": "XXX",
        "country_code": "TH",
        "flightable": True,
    },
]

CITIES = [
    {
        "code": "UTP",
        "name": "Pattaya",
        "country_code": "TH",
        "coordinates": {"lat": 12.9235557, "lon": 100.8824551},
    },
    {
        "code": "BKK",
        "name": "Bangkok",
        "country_code": "TH",
        "coordinates": {"lat": 13.7563309, "lon": 100.5017651},
    },
]


def _mock_datasets():
    respx.get(f"{API_BASE}/data/en/airports.json").mock(
        return_value=httpx.Response(200, json=AIRPORTS)
    )
    respx.get(f"{API_BASE}/data/en/cities.json").mock(return_value=httpx.Response(200, json=CITIES))


def test_haversine_matches_a_known_distance():
    # Bangkok city centre to Suvarnabhumi is ~25 km.
    km = _haversine(13.7563309, 100.5017651, 13.693062, 100.752045)
    assert 25 < km < 30
    assert _haversine(10.0, 20.0, 10.0, 20.0) == 0


@respx.mock
@pytest.mark.asyncio
async def test_nearest_airport_to_a_place_is_not_the_one_named_after_it():
    _mock_datasets()

    result = await find_nearest_airports(near="Pattaya", limit=2)
    assert result["status"] == "ok"
    assert result["origin"]["matched"] == "city"
    assert result["origin"]["code"] == "UTP"
    codes = [a["code"] for a in result["data"]]
    assert codes[0] == "UTP"
    assert "BKK" in codes
    assert result["data"][0]["distance_km"] < result["data"][1]["distance_km"]


@respx.mock
@pytest.mark.asyncio
async def test_unflightable_airports_are_skipped_by_default():
    _mock_datasets()

    default = await find_nearest_airports(near="Pattaya", limit=5)
    assert "ZZZ" not in {a["code"] for a in default["data"]}

    included = await find_nearest_airports(near="Pattaya", limit=5, flightable_only=False)
    assert "ZZZ" in {a["code"] for a in included["data"]}


@respx.mock
@pytest.mark.asyncio
async def test_explicit_coordinates_win_over_a_name():
    _mock_datasets()

    result = await find_nearest_airports(latitude=13.75, longitude=100.5)
    assert result["origin"]["matched"] == "coordinates"
    assert result["data"][0]["code"] in {"DMK", "BKK"}


@respx.mock
@pytest.mark.asyncio
async def test_max_distance_limits_the_radius():
    _mock_datasets()

    result = await find_nearest_airports(near="Pattaya", max_distance_km=50)
    assert {a["code"] for a in result["data"]} == {"UTP"}
    assert result["total"] == 1


@respx.mock
@pytest.mark.asyncio
async def test_nothing_within_the_radius_is_a_hint_not_an_error():
    _mock_datasets()

    result = await find_nearest_airports(near="Pattaya", max_distance_km=1)
    assert result["status"] == "ok"
    assert result["data"] == []
    assert "hint" in result


@respx.mock
@pytest.mark.asyncio
async def test_unresolvable_place_names_the_recovery_tool():
    _mock_datasets()

    result = await find_nearest_airports(near="Nowherecity")
    assert result["status"] == "error"
    assert "lookup_cities" in result["hint"]


@respx.mock
@pytest.mark.asyncio
async def test_missing_and_half_given_coordinates_are_refused():
    _mock_datasets()

    assert (await find_nearest_airports())["status"] == "error"
    assert (await find_nearest_airports(latitude=13.0))["status"] == "error"
    out_of_range = await find_nearest_airports(latitude=91.0, longitude=0.0)
    assert out_of_range["status"] == "error"


@respx.mock
@pytest.mark.asyncio
async def test_airports_without_coordinates_are_ignored_not_crashed_on():
    _mock_datasets()

    result = await find_nearest_airports(near="Pattaya", limit=10, flightable_only=False)
    assert "NOC" not in {a["code"] for a in result["data"]}


@respx.mock
@pytest.mark.asyncio
async def test_bad_coordinates_are_refused_before_the_dataset_is_fetched():
    # Validating after the download meant a missing longitude still paid for a
    # multi-megabyte fetch — and if that fetch failed, the caller got an API
    # error instead of the hint that would have fixed the call.
    airports = respx.get(f"{API_BASE}/data/en/airports.json").mock(
        return_value=httpx.Response(200, json=AIRPORTS)
    )
    cities = respx.get(f"{API_BASE}/data/en/cities.json").mock(
        return_value=httpx.Response(200, json=CITIES)
    )

    bad_calls = (
        {},
        {"latitude": 13.0},
        {"longitude": 100.0},
        {"latitude": 91.0, "longitude": 0.0},
    )
    for kwargs in bad_calls:
        result = await find_nearest_airports(**kwargs)
        assert result["status"] == "error", kwargs
        assert result["hint"], kwargs

    assert airports.call_count == 0
    assert cities.call_count == 0


@respx.mock
@pytest.mark.asyncio
async def test_coordinate_hints_name_the_way_out():
    _mock_datasets()

    half = await find_nearest_airports(latitude=13.0)
    assert "near=" in half["hint"]

    swapped = await find_nearest_airports(latitude=100.0, longitude=13.0)
    assert "swapped" in swapped["hint"]

    neither = await find_nearest_airports()
    assert "Pattaya" in neither["hint"]
