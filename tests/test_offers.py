from urllib.parse import parse_qs, urlsplit

import pytest
import respx

from aviasales_mcp.tools.offers import get_special_offers

OFFERS_URL = "https://api.travelpayouts.com/aviasales/v3/get_special_offers"
OFFER = {
    "origin": "LON", "origin_name": "London", "origin_airport": "LHR",
    "destination": "BCN", "destination_name": "Barcelona", "destination_airport": "BCN",
    "airline": "IB", "airline_title": "Iberia", "flight_number": "169",
    "departure_at": "2026-09-14T10:00:00", "return_at": "2026-09-24T12:00:00",
    "duration": 120, "price": 150, "title": "Barcelona sale", "mini_title": "Sale",
    "link": "/LON1409BCN1?t=IB169&marker=old", "color": "red", "signature": "private",
    "search_id": "internal",
}


def mock_offers(rows=None):
    return respx.get(OFFERS_URL).respond(
        200, json={"success": True, "currency": "eur", "data": [OFFER] if rows is None else rows}
    )


@respx.mock
async def test_special_offers_formats_rows_and_link():
    route = mock_offers()
    result = await get_special_offers(
        " lon ", destination="bcn", airline="ib", currency="EUR", market="US", locale="RU",
        adults=2,
    )
    assert result["status"] == "ok"
    row = result["data"][0]
    assert {key: value for key, value in row.items() if key != "booking_link"} == {
        key: value for key, value in OFFER.items()
        if key not in {"link", "color", "signature", "search_id"}
    }
    link = urlsplit(row["booking_link"])
    assert link.scheme == "https"
    assert link.netloc == "www.aviasales.ru"
    assert link.path == "/search/LON1409BCN2"
    assert parse_qs(link.query) == {"t": ["IB169"], "marker": ["12345"]}
    assert result["currency"] == "eur"
    assert result["passengers"] == {"adults": 2, "children": 0, "infants": 0}
    assert result["trip_class"] == "economy"
    assert "per adult" in result["price_note"]
    assert result["field_note"]
    assert result["price_summary"] == {"min": 150, "median": 150, "max": 150, "count": 1}
    request = route.calls.last.request
    assert dict(request.url.params) == {
        "origin": "LON", "destination": "BCN", "airline": "IB",
        "currency": "eur", "market": "us", "locale": "ru",
    }
    assert request.headers["X-Access-Token"] == "test-token-for-testing"


@respx.mock
async def test_special_offers_keeps_search_prefixed_link():
    mock_offers([{**OFFER, "link": "/search/LON1409BCN1?t=IB169"}])
    result = await get_special_offers("LON", adults=2)
    assert urlsplit(result["data"][0]["booking_link"]).path == "/search/LON1409BCN2"


@pytest.mark.parametrize(
    "fragment", ["@evil.example/x", "//evil.example/x", "/\\evil.example/x", None, ""]
)
@respx.mock
async def test_special_offers_hostile_link(fragment):
    mock_offers([{**OFFER, "link": fragment}])
    result = await get_special_offers("LON", adults=2)
    link = urlsplit(result["data"][0]["booking_link"])
    assert link.scheme == "https"
    assert link.netloc == "www.aviasales.ru"
    assert link.path == "/search/LON1409BCN24092"
    assert parse_qs(link.query)["marker"] == ["12345"]


@respx.mock
async def test_special_offers_empty_keeps_price_note():
    mock_offers([])
    result = await get_special_offers("LON")
    assert result["status"] == "ok"
    assert result["data"] == []
    assert "per adult" in result["price_note"]
    assert result["price_summary"] is None
    assert result["hint"]
    assert (result["total"], result["returned"]) == (0, 0)


@pytest.mark.parametrize("origin", [None, "", "London"])
@respx.mock
async def test_special_offers_requires_origin(origin):
    result = await get_special_offers(origin)
    assert result["status"] == "error"
    assert "origin" in result["error"]
    assert result["hint"]
    assert len(respx.calls) == 0


@pytest.mark.parametrize("airline", ["S77", "S", "S-"])
@respx.mock
async def test_special_offers_rejects_bad_airline(airline):
    result = await get_special_offers("LON", airline=airline)
    assert result["status"] == "error"
    assert "lookup_airlines" in result["hint"]
    assert len(respx.calls) == 0


@respx.mock
async def test_special_offers_limit():
    rows = [{**OFFER, "price": price} for price in (150, 100, 300)]
    mock_offers(rows)
    result = await get_special_offers("LON", limit=2)
    assert (result["total"], result["returned"]) == (3, 2)
    assert [row["price"] for row in result["data"]] == [150, 100]
    assert result["price_summary"] == {"min": 100, "median": 125, "max": 150, "count": 2}


@respx.mock
async def test_special_offers_business_party_and_optional_params(monkeypatch):
    from aviasales_mcp.config import settings

    monkeypatch.setattr(settings, "aviasales_market", "")
    monkeypatch.setattr(settings, "aviasales_locale", "en")
    route = mock_offers()
    result = await get_special_offers("LON", adults=2, children=1, infants=1, trip_class="business")
    assert urlsplit(result["data"][0]["booking_link"]).path == "/search/LON1409BCNc211"
    assert "NOT business-class" in result["price_note"]
    params = route.calls.last.request.url.params
    assert params["locale"] == "en"
    assert all(key not in params for key in ("destination", "airline", "market", "adults"))


@respx.mock
async def test_special_offers_api_error_has_hint():
    respx.get(OFFERS_URL).respond(400, json={"error": "bad request"})
    result = await get_special_offers("LON")
    assert result["status"] == "error"
    assert result["hint"]
    assert "price_note" not in result
