import inspect

import httpx
import pytest
import respx

from aviasales_mcp.tools.flights import (
    _build_booking_link,
    _clamp_party,
    _passenger_block,
    _route_booking_link,
    _validate_trip_class,
    get_alternative_directions,
    get_city_directions,
    get_flexible_date_prices,
    get_latest_prices,
    get_popular_directions,
    get_prices_calendar,
    search_by_price_range,
    search_flights,
)
from aviasales_mcp.validation import InvalidArgumentError

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


def test_booking_link_replaces_an_existing_marker():
    # Appending would leave two markers and no way to tell which one is counted.
    link = _build_booking_link("/search/MOW1607IST1?marker=99999&t=SU100", "1")
    assert link.count("marker=") == 1
    assert "marker=12345" in link
    assert "t=SU100" in link


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
async def test_get_latest_prices_parses_the_v2_shape_it_actually_returns():
    # Despite the /aviasales/v3/ path this endpoint answers in the v2 shape.
    # Parsing it as v3 produced price=None, airline="" and departure_at="" —
    # every field the caller wanted was empty.
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
                        "value": 15000,
                        "gate": "Aviakassa",
                        "depart_date": "2026-05-01T20:35:00+03:00",
                        "return_date": "2026-05-10",
                        "number_of_changes": 1,
                        "duration": 250,
                        "distance": 1755,
                        "found_at": "2026-04-29T12:01:06Z",
                    }
                ],
            },
        )
    )

    result = await get_latest_prices(origin="MOW", limit=5)
    ticket = result["data"][0]
    assert ticket["price"] == 15000
    assert ticket["transfers"] == 1
    assert ticket["duration_total"] == 250
    assert ticket["distance_km"] == 1755
    assert ticket["departure_at"] == "2026-05-01T20:35:00+03:00"
    # `gate` is the selling agency, not an airline — reporting it as the airline
    # mislabelled every row.
    assert ticket["agency"] == "Aviakassa"
    assert ticket["airline"] is None
    # v2 rows carry no link, so it is rebuilt from the route: 01-05 out, 10-05 back.
    assert "/search/MOW0105IST1005" in ticket["booking_link"]
    assert result["price_summary"]["min"] == 15000


@respx.mock
@pytest.mark.asyncio
async def test_get_popular_directions_success():
    # The API keys this on the DESTINATION and returns the origins people fly
    # from; asking with origin alone is a 400.
    respx.get(f"{API_BASE}/aviasales/v3/get_popular_directions").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "currency": "rub",
                "data": {
                    "destination": {"city_name": "Bangkok", "country_name": "Thailand"},
                    "origin": [
                        {"city_name": "Phuket", "city_iata": "HKT", "price": 1663},
                    ],
                },
            },
        )
    )

    result = await get_popular_directions("BKK")
    assert result["destination"]["city_name"] == "Bangkok"
    assert result["data"][0]["city_iata"] == "HKT"


@respx.mock
@pytest.mark.asyncio
async def test_get_city_directions_success():
    respx.get(f"{API_BASE}/v1/city-directions").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "currency": "rub",
                "data": {
                    "EVN": {
                        "origin": "MOW",
                        "destination": "EVN",
                        "price": 18763,
                        "airline": "5G",
                        "departure_at": "2026-10-19T03:10:00+03:00",
                        "return_at": "",
                        "transfers": 0,
                    }
                },
            },
        )
    )

    result = await get_city_directions("MOW")
    assert result["data"]["EVN"]["price"] == 18763
    assert result["price_summary"]["count"] == 1


@respx.mock
@pytest.mark.asyncio
async def test_get_flexible_date_prices_sorts_cheapest_first():
    respx.get(f"{API_BASE}/v2/prices/week-matrix").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "currency": "rub",
                "data": [
                    {
                        "origin": "MOW",
                        "destination": "BKK",
                        "depart_date": "2026-09-10",
                        "return_date": "2026-09-20",
                        "value": 52000,
                        "gate": "Biletix",
                        "number_of_changes": 1,
                        "duration": 2705,
                    },
                    {
                        "origin": "MOW",
                        "destination": "BKK",
                        "depart_date": "2026-09-14",
                        "return_date": "2026-09-21",
                        "value": 44761,
                        "gate": "Biletix",
                        "number_of_changes": 1,
                        "duration": 2705,
                    },
                ],
            },
        )
    )

    result = await get_flexible_date_prices("MOW", "BKK", "2026-09-10", "2026-09-20")
    assert [t["price"] for t in result["data"]] == [44761, 52000]
    assert result["price_summary"]["min"] == 44761


@pytest.mark.asyncio
async def test_get_flexible_date_prices_rejects_a_month():
    result = await get_flexible_date_prices("MOW", "BKK", "2026-09")
    assert result["status"] == "error"
    assert "get_prices_calendar" in result["error"]


@respx.mock
@pytest.mark.asyncio
async def test_search_by_price_range_success():
    route = respx.get(f"{API_BASE}/aviasales/v3/search_by_price_range").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "currency": "rub",
                "data": [
                    {
                        "origin_code": "MOW",
                        "origin_name": "Москва",
                        "origin_airport": "SVO",
                        "destination_code": "KZN",
                        "destination_name": "Казань",
                        "destination_airport": "KZN",
                        "price": 12000,
                        "departure_at": "2026-09-28",
                        "return_at": "2026-10-12",
                        "transfers": 0,
                        "duration": 105,
                        "link": "/search/MOW2809KZN12101",
                    }
                ],
            },
        )
    )

    result = await search_by_price_range("MOW", 10000, 30000)
    assert result["data"][0]["destination"] == "KZN"
    assert result["data"][0]["destination_name"] == "Казань"
    assert "aviasales.ru" in result["data"][0]["booking_link"]
    assert route.calls[0].request.url.params["value_max"] == "30000"


@pytest.mark.asyncio
async def test_search_by_price_range_rejects_an_inverted_band():
    result = await search_by_price_range("MOW", 30000, 10000)
    assert result["status"] == "error"
    assert "value_min" in result["error"]


def test_search_by_price_range_takes_no_dates():
    # The endpoint ignores departure_at/return_at — a December date comes back
    # with the same July fares — so the arguments must not exist and imply
    # a filter that never happens.
    params = inspect.signature(search_by_price_range).parameters
    assert "departure_at" not in params
    assert "return_at" not in params


@respx.mock
@pytest.mark.asyncio
async def test_city_directions_links_are_rebuilt_from_the_route():
    # /v1/city-directions returns no `link`, so without this every result is
    # unclickable and unattributed.
    respx.get(f"{API_BASE}/v1/city-directions").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "currency": "rub",
                "data": {
                    "EVN": {
                        "origin": "MOW",
                        "destination": "EVN",
                        "price": 18763,
                        "departure_at": "2026-10-19T03:10:00+03:00",
                        "return_at": "2026-11-19T23:45:00+04:00",
                        "transfers": 0,
                    }
                },
            },
        )
    )

    result = await get_city_directions("MOW")
    link = result["data"]["EVN"]["booking_link"]
    assert "/search/MOW1910EVN1911" in link
    assert "marker=12345" in link


@respx.mock
@pytest.mark.asyncio
async def test_flexible_dates_refuses_a_month_for_the_return_too():
    route = respx.get(f"{API_BASE}/v2/prices/week-matrix").mock(
        return_value=httpx.Response(200, json={"success": True, "data": []})
    )

    # The API answers a month with `return_date: string doesn't match any date
    # formats`, so spending the request on it is pointless.
    result = await get_flexible_date_prices("MOW", "BKK", "2026-09-10", "2026-10")
    assert result["status"] == "error"
    assert "return_date" in result["error"]
    assert route.call_count == 0


def test_validate_trip_class():
    assert _validate_trip_class("business") == "business"
    assert _validate_trip_class("  Business  ") == "business"
    assert _validate_trip_class("FIRST") == "first"
    # A class the deep link cannot express is refused rather than quietly
    # downgraded: silently answering with economy prices hides the mismatch.
    with pytest.raises(InvalidArgumentError):
        _validate_trip_class("premium-platinum")
    with pytest.raises(InvalidArgumentError):
        _validate_trip_class("")


@respx.mock
@pytest.mark.asyncio
async def test_unsupported_trip_class_is_an_error_not_a_silent_downgrade():
    _mock_prices_for_dates(link="/search/MOW1004LED15041")

    result = await search_flights("MOW", "LED", trip_class="premium-platinum")
    assert result["status"] == "error"
    assert "trip_class" in result["error"]
    assert result["data"] == []


@respx.mock
@pytest.mark.asyncio
async def test_business_class_price_note_warns_prices_are_economy():
    _mock_prices_for_dates()

    economy = await search_flights("MOW", "LED")
    assert "NOT" not in economy["price_note"]

    business = await search_flights("MOW", "LED", trip_class="business")
    assert "business" in business["price_note"]
    assert "NOT" in business["price_note"]


@respx.mock
@pytest.mark.asyncio
async def test_party_sizes_are_clamped():
    _mock_prices_for_dates(link="/search/MOW1004LED15041")

    result = await search_flights("MOW", "LED", adults=99, children=-3, infants=42)
    assert result["passengers"] == {"adults": 9, "children": 0, "infants": 8}
    assert "/search/MOW1004LED1504908" in result["data"][0]["booking_link"]


def test_seated_passengers_cannot_exceed_nine():
    # Aviasales resets /search/MOW2509BKK92 (9 adults + 2 children) to a single
    # passenger, so the excess has to be trimmed before the link is built.
    assert _clamp_party(9, 2, 0) == (9, 0, 0)
    assert _clamp_party(8, 5, 0) == (8, 1, 0)
    assert _clamp_party(8, 1, 0) == (8, 1, 0)
    assert _clamp_party(2, 3, 0) == (2, 3, 0)


def test_infants_cannot_outnumber_adults():
    assert _clamp_party(1, 0, 2) == (1, 0, 1)
    assert _clamp_party(2, 0, 2) == (2, 0, 2)
    assert _clamp_party(3, 0, 9) == (3, 0, 3)


@respx.mock
@pytest.mark.asyncio
async def test_get_alternative_directions_success():
    respx.get(f"{API_BASE}/v2/prices/nearest-places-matrix").mock(
        return_value=httpx.Response(
            200,
            json={
                "origins": ["MOW", "LED"],
                "destinations": ["BKK", "UTP"],
                "prices": [
                    {
                        "origin": "LED",
                        "destination": "UTP",
                        "depart_date": "2026-09-25",
                        "return_date": "",
                        "value": 41000,
                        "gate": "Biletix",
                        "number_of_changes": 1,
                        "duration": 900,
                    }
                ],
            },
        )
    )

    result = await get_alternative_directions("MOW", "BKK")
    assert result["origins"] == ["MOW", "LED"]
    ticket = result["data"][0]
    assert ticket["price"] == 41000
    assert ticket["agency"] == "Biletix"
    assert "/search/LED2509UTP1" in ticket["booking_link"]


def test_route_booking_link_is_built_from_dates():
    link = _route_booking_link("MOW", "BKK", "2026-09-14", "2026-09-21", "2")
    assert link.startswith("https://www.aviasales.ru/search/MOW1409BKK21092")
    assert "marker=12345" in link


def test_route_booking_link_handles_one_way_and_junk():
    assert "/search/MOW1409BKK1" in _route_booking_link("MOW", "BKK", "2026-09-14", "")
    assert _route_booking_link("MOW", "BKK", "not-a-date", "") == ""
    assert _route_booking_link("", "BKK", "2026-09-14", "") == ""


@respx.mock
@pytest.mark.asyncio
async def test_bad_iata_code_is_refused_without_calling_the_api():
    route = respx.get(f"{API_BASE}/aviasales/v3/prices_for_dates").mock(
        return_value=httpx.Response(200, json={"success": True, "data": []})
    )

    result = await search_flights("Moscow", "LED")
    assert result["status"] == "error"
    assert "lookup_cities" in result["error"]
    # The whole point is not spending a request on a query that cannot work.
    assert route.call_count == 0


@respx.mock
@pytest.mark.asyncio
async def test_bad_date_is_refused_without_calling_the_api():
    route = respx.get(f"{API_BASE}/aviasales/v3/prices_for_dates").mock(
        return_value=httpx.Response(200, json={"success": True, "data": []})
    )

    result = await search_flights("MOW", "LED", departure_at="29.07.2026")
    assert result["status"] == "error"
    assert "YYYY-MM-DD" in result["error"]
    assert route.call_count == 0

    impossible = await search_flights("MOW", "LED", departure_at="2026-13-40")
    assert impossible["status"] == "error"
    assert route.call_count == 0


@respx.mock
@pytest.mark.asyncio
async def test_empty_result_says_so_instead_of_looking_like_no_route():
    respx.get(f"{API_BASE}/aviasales/v3/prices_for_dates").mock(
        return_value=httpx.Response(200, json={"success": True, "currency": "rub", "data": []})
    )

    result = await search_flights("MOW", "LED")
    assert result["status"] == "ok"
    assert result["data"] == []
    assert "hint" in result
    assert result["price_summary"] is None


@respx.mock
@pytest.mark.asyncio
async def test_market_and_currency_come_from_settings(monkeypatch):
    from aviasales_mcp.tools import flights as flights_module

    monkeypatch.setattr(flights_module.settings, "aviasales_market", "us")
    monkeypatch.setattr(flights_module.settings, "aviasales_default_currency", "usd")
    route = respx.get(f"{API_BASE}/aviasales/v3/prices_for_dates").mock(
        return_value=httpx.Response(200, json={"success": True, "currency": "usd", "data": []})
    )

    await search_flights("LON", "NYC")
    params = route.calls[0].request.url.params
    # The price cache is per market: the same route in the same currency is
    # priced differently for market=ru and market=us.
    assert params["market"] == "us"
    assert params["currency"] == "usd"

    await search_flights("LON", "NYC", market="th", currency="thb")
    params = route.calls[1].request.url.params
    assert params["market"] == "th"
    assert params["currency"] == "thb"


@pytest.mark.asyncio
async def test_bad_market_is_refused():
    result = await search_flights("MOW", "LED", market="usa")
    assert result["status"] == "error"
    assert "market" in result["error"]


@respx.mock
@pytest.mark.asyncio
async def test_departure_time_window_filters_results():
    respx.get(f"{API_BASE}/aviasales/v3/prices_for_dates").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "currency": "rub",
                "data": [
                    {"origin": "MOW", "destination": "LED", "price": 1,
                     "departure_at": "2026-04-10T07:30:00+03:00", "link": ""},
                    {"origin": "MOW", "destination": "LED", "price": 2,
                     "departure_at": "2026-04-10T21:15:00+03:00", "link": ""},
                    {"origin": "MOW", "destination": "LED", "price": 3,
                     "departure_at": "", "link": ""},
                ],
            },
        )
    )

    evening = await search_flights("MOW", "LED", depart_after="20:00")
    assert [t["price"] for t in evening["data"]] == [2]
    assert evening["time_filter"] == {
        "depart_after": "20:00",
        "depart_before": None,
        "considered": 3,
        "matched": 1,
    }

    morning = await search_flights("MOW", "LED", depart_before="12:00")
    assert [t["price"] for t in morning["data"]] == [1]


@respx.mock
@pytest.mark.asyncio
async def test_departure_window_can_wrap_midnight():
    respx.get(f"{API_BASE}/aviasales/v3/prices_for_dates").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "currency": "rub",
                "data": [
                    {"origin": "MOW", "destination": "LED", "price": 1,
                     "departure_at": "2026-04-10T23:40:00+03:00", "link": ""},
                    {"origin": "MOW", "destination": "LED", "price": 2,
                     "departure_at": "2026-04-10T04:10:00+03:00", "link": ""},
                    {"origin": "MOW", "destination": "LED", "price": 3,
                     "departure_at": "2026-04-10T13:00:00+03:00", "link": ""},
                ],
            },
        )
    )

    red_eyes = await search_flights("MOW", "LED", depart_after="22:00", depart_before="06:00")
    assert sorted(t["price"] for t in red_eyes["data"]) == [1, 2]


@pytest.mark.asyncio
async def test_bad_time_window_is_refused():
    result = await search_flights("MOW", "LED", depart_after="8pm")
    assert result["status"] == "error"
    assert "HH:MM" in result["error"]


@respx.mock
@pytest.mark.asyncio
async def test_price_summary_reports_the_spread():
    respx.get(f"{API_BASE}/aviasales/v3/prices_for_dates").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "currency": "rub",
                "data": [
                    {"origin": "MOW", "destination": "LED", "price": 3000, "link": ""},
                    {"origin": "MOW", "destination": "LED", "price": 5000, "link": ""},
                    {"origin": "MOW", "destination": "LED", "price": 9000, "link": ""},
                ],
            },
        )
    )

    result = await search_flights("MOW", "LED")
    assert result["price_summary"] == {"min": 3000, "median": 5000, "max": 9000, "count": 3}


@respx.mock
@pytest.mark.asyncio
async def test_unexpected_payload_returns_an_error_not_a_protocol_failure():
    # A shape change upstream must not escape the tool as a JSON-RPC error, and
    # the exception text must not be echoed into the conversation.
    respx.get(f"{API_BASE}/aviasales/v3/prices_for_dates").mock(
        return_value=httpx.Response(200, json={"success": True, "data": [["not", "a", "dict"]]})
    )

    result = await search_flights("MOW", "LED")
    assert result["status"] == "error"
    assert result["error"] == "Internal server error — see server logs"
    assert result["data"] == []


def test_clamped_party_always_encodes_a_valid_block():
    for adults in range(-2, 12):
        for children in range(-2, 12):
            for infants in range(-2, 12):
                a, c, i = _clamp_party(adults, children, infants)
                assert 1 <= a <= 9
                assert 0 <= c <= 8
                assert 0 <= i <= 8
                assert a + c <= 9
                assert i <= a
                assert _passenger_block(a, c, i, "economy").isdigit()
