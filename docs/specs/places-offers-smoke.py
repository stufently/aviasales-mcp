"""Independent contract smoke for the places-offers milestone.

Written by the spec author before the work. The executor must not edit it.
Run inside the dev image with PYTHONPATH=/app/src; exits 0 only when every
check passes. No network: every HTTP call is respx-mocked, and a call that
was not mocked fails the check.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tomllib
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

os.environ.setdefault("AVIASALES_API_TOKEN", "smoke-token")
os.environ.setdefault("AVIASALES_PARTNER_ID", "12345")

import httpx  # noqa: E402
import respx  # noqa: E402

API = "https://api.travelpayouts.com"
PLACES = "https://autocomplete.travelpayouts.com/places2"
ROOT = Path(__file__).resolve().parents[2]

PLACE_ROWS = [
    {
        "id": "x1",
        "type": "city",
        "code": "LON",
        "name": "London",
        "country_code": "GB",
        "country_name": "United Kingdom",
        "state_code": None,
        "coordinates": {"lon": -0.12, "lat": 51.5},
        "index_strings": ["londres"],
        "weight": 122275,
        "cases": None,
        "country_cases": None,
        "main_airport_name": None,
    },
    {
        "id": "x2",
        "type": "airport",
        "code": "LHR",
        "name": "Heathrow",
        "country_code": "GB",
        "country_name": "United Kingdom",
        "city_code": "LON",
        "city_name": "London",
        "state_code": None,
        "coordinates": {"lon": -0.45, "lat": 51.47},
        "index_strings": [],
        "weight": 37554,
        "cases": None,
        "city_cases": None,
        "country_cases": None,
    },
    {
        "id": "x3",
        "type": "airport",
        "code": "LGW",
        "name": "Gatwick",
        "country_code": "GB",
        "country_name": "United Kingdom",
        "city_code": "LON",
        "city_name": "London",
        "state_code": None,
        "coordinates": {"lon": -0.19, "lat": 51.15},
        "index_strings": [],
        "weight": 15351,
        "cases": None,
        "city_cases": None,
        "country_cases": None,
    },
]

OFFER = {
    "airline": "N4",
    "airline_title": "Nordwind Airlines",
    "color": "CD202C",
    "departure_at": "2026-09-14T08:55:00+03:00",
    "destination": "BCN",
    "destination_airport": "BCN",
    "destination_name": "Barcelona",
    "duration": 85,
    "flight_number": "177",
    "link": "/LON1409BCN1?t=N416315989001631604000000000SVOBCN_3d50_1413&search_date=29072026",
    "mini_title": "Flight deals from London",
    "origin": "LON",
    "origin_airport": "LHR",
    "origin_name": "London",
    "price": 1413,
    "search_id": "9a904680",
    "signature": "3d507ff7",
    "title": "Flight deals from London to Barcelona",
}

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS " if ok else "FAIL ") + name + (f" :: {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def qs(request: httpx.Request) -> dict[str, list[str]]:
    return parse_qs(urlsplit(str(request.url)).query, keep_blank_values=True)


async def places_checks() -> None:
    from aviasales_mcp.tools.places import find_places

    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(PLACES).mock(return_value=httpx.Response(200, json=PLACE_ROWS))
        api = mock.route(host="api.travelpayouts.com").mock(return_value=httpx.Response(500))
        res = await find_places(term="lond", locale="ru", limit=2)
        check("places: status ok", res.get("status") == "ok", json.dumps(res)[:300])
        check("places: one upstream call", route.call_count == 1, str(route.call_count))
        check("places: never touches api.travelpayouts.com", api.call_count == 0)
        if route.call_count:
            req = route.calls[0].request
            q = qs(req)
            check(
                "places: types[] defaults to city+airport",
                q.get("types[]") == ["city", "airport"],
                str(q),
            )
            check(
                "places: term and locale sent",
                q.get("term") == ["lond"] and q.get("locale") == ["ru"],
                str(q),
            )
            check(
                "places: no X-Access-Token header",
                "x-access-token" not in req.headers,
                str(dict(req.headers)),
            )
        data = res.get("data") or []
        check("places: limit applied", len(data) == 2, str(len(data)))
        check(
            "places: total/returned/truncated",
            res.get("total") == 3 and res.get("returned") == 2 and res.get("truncated") is True,
            json.dumps({k: res.get(k) for k in ("total", "returned", "truncated")}),
        )
        check(
            "places: upstream order kept",
            [d.get("code") for d in data] == ["LON", "LHR"],
            str([d.get("code") for d in data]),
        )
        if data:
            dropped = {"id", "index_strings", "weight", "cases", "city_cases", "country_cases"}
            check(
                "places: service fields dropped",
                not (dropped & set(data[0]) | dropped & set(data[1])),
                str(sorted(set(data[0]) | set(data[1]))),
            )
            check(
                "places: useful fields kept",
                data[1].get("city_code") == "LON"
                and data[1].get("type") == "airport"
                and data[0].get("coordinates") == {"lon": -0.12, "lat": 51.5},
                json.dumps(data),
            )

    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(PLACES).mock(return_value=httpx.Response(200, json=[]))
        res = await find_places(term="thai", types=["country", "country"], locale=None)
        q = qs(route.calls[0].request) if route.call_count else {}
        check("places: explicit types deduplicated", q.get("types[]") == ["country"], str(q))
        check("places: default locale is the server's", q.get("locale") == ["en"], str(q))
        check(
            "places: empty result is ok with a hint",
            res.get("status") == "ok" and res.get("data") == [] and bool(res.get("hint")),
            json.dumps(res)[:300],
        )

    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(PLACES).mock(return_value=httpx.Response(200, json=PLACE_ROWS))
        res = await find_places(term=" l ")
        check(
            "places: too-short term rejected before any call",
            res.get("status") == "error"
            and bool(res.get("hint"))
            and route.call_count == 0
            and "term" in str(res.get("error")),
            json.dumps(res)[:300],
        )
        res = await find_places(term="lond", locale="english")
        check(
            "places: bad locale rejected before any call",
            res.get("status") == "error"
            and route.call_count == 0
            and "locale" in str(res.get("error")),
            json.dumps(res)[:300],
        )

    with respx.mock(assert_all_called=False) as mock:
        mock.get(PLACES).mock(return_value=httpx.Response(200, json={"oops": 1}))
        res = await find_places(term="lond")
        check(
            "places: non-list payload is an error with a hint",
            res.get("status") == "error" and bool(res.get("hint")),
            json.dumps(res)[:300],
        )


async def offers_checks() -> None:
    from aviasales_mcp.tools.offers import get_special_offers

    url = f"{API}/aviasales/v3/get_special_offers"
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(url).mock(
            return_value=httpx.Response(
                200, json={"success": True, "currency": "usd", "data": [OFFER]}
            )
        )
        res = await get_special_offers(
            origin="lon", destination="bcn", airline="n4", currency="usd", adults=2
        )
        check("offers: status ok", res.get("status") == "ok", json.dumps(res)[:300])
        if route.call_count:
            req = route.calls[0].request
            q = qs(req)
            check(
                "offers: codes normalised and sent",
                q.get("origin") == ["LON"]
                and q.get("destination") == ["BCN"]
                and q.get("airline") == ["N4"]
                and q.get("currency") == ["usd"],
                str(q),
            )
            check("offers: token header sent", req.headers.get("x-access-token") == "smoke-token")
        else:
            check("offers: one upstream call", False, "no call")
        data = res.get("data") or []
        check("offers: one row", len(data) == 1, str(len(data)))
        row = data[0] if data else {}
        link = row.get("booking_link", "")
        check(
            "offers: link gets /search/ and the party block",
            link.startswith("https://www.aviasales.ru/search/LON1409BCN2?"),
            link,
        )
        check(
            "offers: link carries the marker once",
            parse_qs(urlsplit(link).query).get("marker") == ["12345"],
            link,
        )
        check(
            "offers: service fields dropped",
            not ({"color", "signature", "search_id", "link"} & set(row)),
            str(sorted(row)),
        )
        check(
            "offers: offer fields kept",
            row.get("price") == 1413
            and row.get("airline_title") == "Nordwind Airlines"
            and row.get("title") == OFFER["title"]
            and row.get("origin_name") == "London",
            json.dumps(row),
        )
        check(
            "offers: price contract",
            bool(res.get("price_note"))
            and (res.get("price_summary") or {}).get("min") == 1413
            and res.get("currency") == "usd",
            json.dumps({k: res.get(k) for k in ("price_note", "price_summary", "currency")}),
        )
        check(
            "offers: passengers echoed",
            res.get("passengers") == {"adults": 2, "children": 0, "infants": 0},
            str(res.get("passengers")),
        )

    with respx.mock(assert_all_called=False) as mock:
        bad = dict(OFFER, link="@evil.example/x")
        mock.get(url).mock(
            return_value=httpx.Response(
                200, json={"success": True, "currency": "rub", "data": [bad]}
            )
        )
        res = await get_special_offers(origin="LON")
        link = (res.get("data") or [{}])[0].get("booking_link", "")
        check(
            "offers: hostile link never leaves the booking host",
            "evil" not in link and (link == "" or link.startswith("https://www.aviasales.ru/")),
            link,
        )

    with respx.mock(assert_all_called=False) as mock:
        mock.get(url).mock(
            return_value=httpx.Response(200, json={"success": True, "currency": "rub", "data": []})
        )
        res = await get_special_offers(origin="LON")
        check(
            "offers: empty result keeps price_note and a hint",
            res.get("status") == "ok"
            and res.get("data") == []
            and bool(res.get("hint"))
            and bool(res.get("price_note"))
            and res.get("price_summary") is None,
            json.dumps(res)[:300],
        )

    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(url).mock(return_value=httpx.Response(200, json={"data": []}))
        res = await get_special_offers(origin=None)
        check(
            "offers: origin is required (no IP geolocation of the server)",
            res.get("status") == "error"
            and route.call_count == 0
            and "origin" in str(res.get("error")),
            json.dumps(res)[:300],
        )
        res = await get_special_offers(origin="LON", airline="S77")
        check(
            "offers: bad airline code rejected before any call",
            res.get("status") == "error"
            and bool(res.get("hint"))
            and route.call_count == 0
            and "airline" in str(res.get("error")),
            json.dumps(res)[:300],
        )


async def duration_checks() -> None:
    from aviasales_mcp.tools.flights import get_prices_calendar

    url = f"{API}/aviasales/v3/grouped_prices"
    body = {"success": True, "currency": "rub", "data": {}}
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(url).mock(return_value=httpx.Response(200, json=body))
        res = await get_prices_calendar(
            origin="MOW",
            destination="BKK",
            departure_at="2026-09",
            min_trip_duration=10,
            max_trip_duration=14,
        )
        q = qs(route.calls[0].request) if route.call_count else {}
        check(
            "duration: both bounds sent",
            q.get("min_trip_duration") == ["10"] and q.get("max_trip_duration") == ["14"],
            str(q),
        )
        check(
            "duration: echoed in payload",
            res.get("trip_duration") == {"min": 10, "max": 14},
            str(res.get("trip_duration")),
        )

        await get_prices_calendar(origin="MOW", destination="BKK", min_trip_duration=7)
        q = qs(route.calls[1].request) if route.call_count > 1 else {}
        check(
            "duration: one bound alone",
            q.get("min_trip_duration") == ["7"] and "max_trip_duration" not in q,
            str(q),
        )

        res = await get_prices_calendar(origin="MOW", destination="BKK")
        q = qs(route.calls[2].request) if route.call_count > 2 else {}
        check(
            "duration: absent when unset",
            "min_trip_duration" not in q
            and "max_trip_duration" not in q
            and "trip_duration" not in res,
            str(q),
        )

        before = route.call_count
        res = await get_prices_calendar(
            origin="MOW", destination="BKK", min_trip_duration=14, max_trip_duration=10
        )
        check(
            "duration: min > max rejected before any call",
            res.get("status") == "error"
            and bool(res.get("hint"))
            and "min_trip_duration" in str(res.get("error"))
            and route.call_count == before,
            json.dumps(res)[:300],
        )
        res = await get_prices_calendar(origin="MOW", destination="BKK", min_trip_duration=0)
        check(
            "duration: zero rejected before any call (direct call bypasses schema)",
            res.get("status") == "error"
            and "min_trip_duration" in str(res.get("error"))
            and route.call_count == before,
            json.dumps(res)[:300],
        )


async def server_checks() -> None:
    from aviasales_mcp import server

    tools = {t.name: t for t in await server.mcp.list_tools()}
    check("server: 15 tools", len(tools) == 15, str(sorted(tools)))
    check("server: new tools registered", {"find_places", "get_special_offers"} <= set(tools))
    cal = tools.get("get_prices_calendar")
    props = cal.parameters["properties"] if cal else {}
    check(
        "server: duration bounds reach the schema",
        "min_trip_duration" in props
        and "max_trip_duration" in props
        and "min_trip_duration" not in (cal.parameters.get("required") or []),
        json.dumps(props.get("min_trip_duration")),
    )
    fp = tools.get("find_places")
    if fp:
        p = fp.parameters
        check(
            "server: find_places requires term only",
            p.get("required") == ["term"],
            str(p.get("required")),
        )
        check(
            "server: find_places limit max 20",
            p["properties"].get("limit", {}).get("maximum") == 20,
            json.dumps(p["properties"].get("limit")),
        )
        check(
            "server: find_places types enum in schema",
            {"city", "airport", "country"}
            <= set(
                re.findall(r'"(city|airport|country)"', json.dumps(p["properties"].get("types")))
            ),
            json.dumps(p["properties"].get("types")),
        )
    so = tools.get("get_special_offers")
    if so:
        check(
            "server: get_special_offers requires origin",
            "origin" in (so.parameters.get("required") or []),
            str(so.parameters.get("required")),
        )
    for name in ("find_places", "get_special_offers"):
        t = tools.get(name)
        check(
            f"server: {name} is read-only", bool(t and t.annotations and t.annotations.readOnlyHint)
        )


def version_checks() -> None:
    py = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    sj = json.loads((ROOT / "server.json").read_text())
    pkg_versions = {p["version"] for p in sj.get("packages", []) if "version" in p}
    oci = [
        p.get("identifier", "") for p in sj.get("packages", []) if p.get("registryType") == "oci"
    ]
    check("version: pyproject is 0.6.0", py == "0.6.0", py)
    check(
        "version: server.json matches",
        sj.get("version") == py
        and pkg_versions == {py}
        and bool(oci)
        and all(i.endswith(f":{py}") for i in oci),
        f"{sj.get('version')} {pkg_versions} {oci}",
    )
    manifest = json.loads((ROOT / "mcpb/manifest.json").read_text())
    names = {t["name"] for t in manifest.get("tools", [])}
    check(
        "manifest: lists the 15 tools",
        len(names) == 15 and {"find_places", "get_special_offers"} <= names,
        str(sorted(names)),
    )
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    check("ci: smoke expects 15 tools", '[ "$count" = 15 ]' in ci)


async def main() -> None:
    for step in (places_checks, offers_checks, duration_checks, server_checks):
        try:
            await step()
        except Exception as exc:  # report and keep going
            check(f"{step.__name__}: raised", False, f"{type(exc).__name__}: {exc}")
    try:
        version_checks()
    except Exception as exc:
        check("version_checks: raised", False, f"{type(exc).__name__}: {exc}")
    from aviasales_mcp.api import client

    await client.aclose()


asyncio.run(main())
print(f"{len(failures)} failed")
sys.exit(1 if failures else 0)
