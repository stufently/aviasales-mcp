import pytest
import respx

from aviasales_mcp.tools.places import find_places

PLACES_URL = "https://autocomplete.travelpayouts.com/places2"


@respx.mock
async def test_find_places_sends_types_without_token():
    route = respx.get(PLACES_URL).respond(200, json=[{"type": "city", "code": "BKK"}])
    result = await find_places(" bangk ", locale="RU")
    request = route.calls.last.request
    assert request.url.params["term"] == "bangk"
    assert request.url.params["locale"] == "ru"
    assert request.url.params.get_list("types[]") == ["city", "airport"]
    assert "types" not in request.url.params
    assert "X-Access-Token" not in request.headers
    assert all(call.request.url.host == "autocomplete.travelpayouts.com" for call in respx.calls)
    assert result["status"] == "ok"
    assert result["term"] == "bangk"
    assert result["locale"] == "ru"
    assert result["types"] == ["city", "airport"]


@respx.mock
async def test_find_places_limit_and_whitelist():
    public = {
        "type": "airport", "code": "BKK", "name": "Suvarnabhumi",
        "city_code": "BKK", "city_name": "Bangkok", "country_code": "TH",
        "country_name": "Thailand", "state_code": "10", "main_airport_name": "BKK",
        "coordinates": {"lon": 100.75, "lat": 13.69},
    }
    private = dict.fromkeys(
        ("id", "index_strings", "weight", "cases", "city_cases", "country_cases"), "internal"
    )
    respx.get(PLACES_URL).respond(200, json=[{**public, **private}, {"code": "DMK"}])
    result = await find_places("bang", limit=1)
    assert result["data"] == [public]
    assert (result["total"], result["returned"], result["truncated"]) == (2, 1, True)


@respx.mock
async def test_find_places_dedups_types():
    route = respx.get(PLACES_URL).respond(200, json=[{"code": "TH"}])
    result = await find_places("thai", types=["country", "country"])
    assert route.calls.last.request.url.params.get_list("types[]") == ["country"]
    assert result["types"] == ["country"]


@respx.mock
async def test_find_places_empty_types_uses_default():
    route = respx.get(PLACES_URL).respond(200, json=[{"type": "city", "code": "BKK"}])
    result = await find_places("bang", types=[])
    assert route.calls.last.request.url.params.get_list("types[]") == ["city", "airport"]
    assert result["types"] == ["city", "airport"]


@respx.mock
async def test_find_places_rejects_short_term():
    result = await find_places(" l ")
    assert result["status"] == "error"
    assert "term" in result["error"]
    assert result["hint"]
    assert len(respx.calls) == 0


@respx.mock
async def test_find_places_non_list_is_error():
    respx.get(PLACES_URL).respond(200, json={"oops": 1})
    result = await find_places("bang")
    assert result["status"] == "error"
    assert result["hint"]
    assert (result["total"], result["returned"], result["truncated"]) == (0, 0, False)


@respx.mock
async def test_find_places_empty_has_hint():
    respx.get(PLACES_URL).respond(200, json=[])
    result = await find_places("unknown")
    assert result["status"] == "ok"
    assert result["data"] == []
    assert (result["total"], result["returned"], result["truncated"]) == (0, 0, False)
    assert "lookup_cities" in result["hint"]


@respx.mock
async def test_find_places_discards_non_objects_and_keeps_order():
    respx.get(PLACES_URL).respond(200, json=[None, {"code": "DMK"}, 1, {"code": "BKK"}])
    result = await find_places("bang")
    assert result["data"] == [{"code": "DMK"}, {"code": "BKK"}]
    assert (result["total"], result["returned"], result["truncated"]) == (4, 2, True)


@pytest.mark.parametrize("kwargs", [{"types": ["town"]}, {"locale": "eng"}])
@respx.mock
async def test_find_places_rejects_invalid_arguments(kwargs):
    result = await find_places("bang", **kwargs)
    assert result["status"] == "error"
    assert result["hint"]
    assert len(respx.calls) == 0
