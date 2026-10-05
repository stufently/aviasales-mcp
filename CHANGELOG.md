# Changelog

## Unreleased

### Changed
- Docker base image `python:3.13-slim` → `python:3.14-slim` (3.14.8, Debian 13);
  CI test matrix gains 3.14, `requires-python >=3.12` unchanged. Verified in
  Docker on 3.14.8: ruff clean, 148 tests, coverage 96.77%, runtime import OK.

## 0.5.0 — 2026-08-21

Two defects found during the packaging pass, both in the contract between the
tools and the model rather than in the API calls.

### Fixed
- **`get_popular_directions` and `get_alternative_directions` returned no
  `price_note`.** Every other price tool ships one, and it is the field that
  says the number is *per adult in economy* — so on these two the model had
  nothing telling it the fare was not the party total, and could quote a
  one-adult price as the cost for a family. Both now carry `price_note`, and
  `price_summary` (min/median/max/count) with it. The note survives an empty
  result, where `price_summary` is honestly `null`
- **Validation errors came back without a `hint`.** `guard` passed `None` for
  `InvalidArgumentError`, so the one failure class a model can always fix
  unaided was the only one that arrived with no guidance — while the README
  promised a hint on every error. `InvalidArgumentError` now carries its own
  `hint`, and every validator sets one that names the substitute and the tool
  that produces it ("look the name up with `lookup_cities` and retry with the
  code it returns", "pick a day inside 2026-10, or use `get_prices_calendar`").
  The generic fallback also states that no API call was made, so an unchanged
  retry is pointless — the API-failure hint used to imply the opposite
- **`find_nearest_airports` validated its coordinates after downloading the
  airport dataset.** A half-given pair (`latitude` with no `longitude`) still
  paid for a multi-megabyte fetch, and when that fetch failed the caller got an
  API error instead of the hint naming the actual mistake. Argument checks now
  run first, which is what the README claimed all along
- **`full_date` handed back a hint offering the format it rejects.** It
  delegates to `date_or_month`, whose hint presents `"YYYY-MM"` as a valid
  option — but the week matrix 400s on a bare month, so a model following that
  hint walked into the next rejection. The hint is now replaced, not inherited

### Changed
- Server version 0.4.0 → 0.5.0: response shape and tool docstrings changed, and
  clients key their tool-definition cache on it
- Tests 128 → 148. New coverage: `price_note`/`price_summary` on both repaired
  tools and on an empty result; a parametrized sweep asserting nine different
  bad arguments each come back with a non-empty, actionable hint; a
  validator-level check that every failure path attaches a hint distinct from
  its error message; and `call_count == 0` assertions proving bad coordinates
  never reach the network
- README restores the two claims weakened in the packaging commit (`price_note`
  on every price response, a `hint` on every error) — the code now matches them
  again. Scope stated precisely: error payloads carry no `price_note`, having no
  price to caveat, and schema-level rejections (`Literal`/`Field` bounds) are
  refused by FastMCP before this code runs, so they surface as JSON-RPC errors
  rather than the `{status, error, hint}` payload. Noted in AGENTS.md

## 2026-08-21 — packaging and discoverability

Distribution-only pass: no tool, schema or runtime behaviour changed.

### Added
- `[project.urls]` (Homepage, Repository, Issues, Changelog) — a PyPI page with
  no links back to the repository is a dead end for anyone who lands on it
- `license-files = ["LICENSE"]`, so the GPL text ships inside the wheel and sdist
  instead of only living in the repository
- `py.typed` marker plus the `Typing :: Typed` classifier — the package ships
  inline type annotations, but without the marker type checkers ignore them in
  downstream projects
- `LICENSE` to the Dockerfile's `COPY`: `license-files` makes it a build input,
  and the image was installing a package with `License-File: None`
- README: an **Install** section (`uvx` / `pip`), copy-paste MCP client configs
  for Claude Code, Claude Desktop and Cursor, and a **Common prompts** table
  mapping plain-language questions to the tools that answer them
- GitHub repository description and topics, which were both empty

### Changed
- Classifiers: `Development Status` 3 → 4 (13 tools, 128 tests, 97% coverage is
  past alpha), plus Environment, Intended Audience, Operating System, Python 3
  and Topic entries that PyPI facets on
- Keywords broadened to the terms the package is actually searched by
  (`mcp-server`, `model-context-protocol`, `flight-search`, `airfare`, `fastmcp`)
- Dropped the `License :: OSI Approved ::` classifier: PEP 639 deprecates license
  classifiers alongside the SPDX `license` expression this project already
  declares, and lets build backends reject the pair — newer ones do
- README no longer claims `price_note` and `price_summary` on *every* price
  response (`get_popular_directions` and `get_alternative_directions` carry
  neither), nor a `hint` on validation errors (there the message itself is the
  guidance). Wording only — the payloads are unchanged

## 2026-07-29 — competitor and API-surface audit

Sweep of every Aviasales/Travelpayouts MCP server on GitHub (`wdvr/mcp-kayak`,
`maratsarbasov/flights-mcp`, `theYahia/travelpayouts-mcp`, `MissiaL/travel-search-ru`,
`MikkoParkkola/trvl`) plus the Google-Flights and Flighty MCP servers, and a
live probe of the whole Travelpayouts endpoint surface against our own token.
Nothing was portable as code — every competitor is behind us on retries,
caching, payload size and testing — but the audit turned up four defects of ours
and several capability gaps.

### Breaking (tool schema and response shape)
- `get_popular_directions` now takes `destination` (required) instead of `origin`, and its `data` is the list of origin cities rather than a keyed map. The old call signature was rejected by the API anyway
- `search_flights` no longer accepts `sorting`; `search_by_price_range` accepts no dates. Both were parameters the endpoint ignores
- v2-shaped rows report `agency` and a null `airline` where they used to report the agency as the airline
- An out-of-range `limit`/party size or an unknown `trip_class` is now refused instead of silently clamped or downgraded

### Fixed
- **`get_latest_prices` returned empty tickets.** Despite its `/aviasales/v3/` path the endpoint answers in the *v2* shape (`value`/`gate`/`depart_date`), and it was being parsed as v3 — so `price`, `airline`, `departure_at`, `return_at`, `expires_at` and `booking_link` came back null or empty on every row. Verified live against the API
- **`get_popular_directions` was documented backwards and 400'd on its own example.** The endpoint requires `destination` and returns the cities travellers fly *from*; the tool advertised "popular destinations from a city" and took `origin`, which the API rejects with `bad request: destination parameter is skipped`. It now takes `destination` and returns the origin list. The "where can I fly from X" question it used to promise is answered by the new `get_city_directions`
- **v2 rows reported the selling agency as the airline.** `gate` is "Kupi.com", "Aviakassa", "Biletix" — an agency, not a carrier. It is now `agency`, and `airline` is null rather than wrong
- **v2 rows and `/v1/city-directions` had no booking link at all**, because those endpoints return no `link`. The Aviasales deep link is now rebuilt from the route and dates, so latest prices, the flexible-date matrix, nearby airports and city directions are clickable — and attributed
- A fragment that already carried a `marker` got a second one appended, leaving the attribution ambiguous. The marker is now replaced, not appended
- `market` was never sent: every deployment read the Russian price cache. LON→NYC in USD is 331 for `market=ru` and 317 for `market=us` (measured). Configurable via `AVIASALES_MARKET` and overridable per call
- Reference data was pinned to English, so `lookup_cities("Мюнхен")` could never match. `locale` is now a parameter (and `AVIASALES_LOCALE` a setting), validated as two letters so it cannot escape the `/data/<locale>/…` path
- Removed `sorting` from `search_flights`: the API only sorts by price when a destination is given, and this tool always gives one, so the option never did anything. Dropped the equally dead `unique=false`

### Added
- Input validation before the API call. A typo'd code or a `29.07.2026` date used to cost a request and return an empty list, which a model reads as "no flights on this route"; it is now refused with the expected format spelled out
- `status` on every response (`"ok"`/`"error"`), so an empty result is never mistaken for a failure, plus a `hint` on errors and empty results naming what to try next
- `get_city_directions` — cheapest destinations reachable from a city (`/v1/city-directions`), the inspiration search the README already promised
- `get_flexible_date_prices` — prices for the days around your dates (`/v2/prices/week-matrix`), answering "would shifting a day be cheaper?"
- `search_by_price_range` — flights inside a budget (`/aviasales/v3/search_by_price_range`); omit the destination to search anywhere
- `find_nearest_airports` — airports closest to a place or to lat/lon, ranked by great-circle distance over the datasets we already cache. Adapted from `wdvr/mcp-kayak`'s idea without its dependencies (no `geopy`, no Nominatim geocoder, no external rate limit)
- `depart_after` / `depart_before` on `search_flights` — keep only departures in a time window, including windows that wrap midnight for red-eyes
- `price_summary` (min/median/max/count) on price responses, so the model can judge a fare without a second search
- `field_note` stating that durations are minutes and timestamps are local airport time — both were bare values the model had to guess at
- Ranked reference lookups: exact code, then exact city code, then name, with unflightable airports last. Slicing raw dataset order buried the hub under whatever heliport came first
- MCP `annotations` (read-only, non-destructive, idempotent, open-world) on all 13 tools, and a server `version` — clients cache tool definitions and had nothing to invalidate on
- `AVIASALES_DEFAULT_CURRENCY`, so a non-RUB deployment no longer depends on the model passing `currency` every time
- Tool descriptions now cross-reference each other (which tool to use instead, and that IATA codes come from `lookup_cities`), and say what to do about intents they cannot serve
- A warning when the published rate-limit budget runs low, instead of discovering it as a 429
- Test suite grown from 73 to 122 tests (97% coverage)

### Changed
- One pooled HTTP client per event loop instead of a fresh `AsyncClient` per request — every call paid a new TLS handshake. Closed on server shutdown via the FastMCP lifespan
- A time-of-day filter now fetches the full result set before filtering. Filtering a small `limit` could report "nothing departs then" from a sample that never contained the answer
- `get_flexible_date_prices` refuses a bare month for either date: the week matrix answers `2026-10` with a 400
- An unsupported `trip_class` is now an error rather than a silent downgrade to economy. Combined with schema-level enums, a typo is refused instead of answered with the wrong cabin's prices
- Bounds (`limit`, party sizes) and enums now reach the model through the tool schema instead of being clamped invisibly
- Tools no longer let unexpected exceptions escape as protocol errors; they are logged server-side and returned as a sanitized error payload

## 2026-07-29

### Changed
- **Breaking:** `lookup_airlines`, `lookup_airports`, `lookup_cities` and `lookup_countries` now take `search` and `limit` (default 50, max 500) and return `{total, returned, truncated, data}` instead of the raw list. They previously returned the entire dataset — `lookup_airports` alone was 10,369 entries / ~2.7 MB / ~680k tokens per call, which no model can hold. A filtered lookup is now ~200 bytes.
- Reference responses drop the `name_translations` and `cases` blobs, which duplicate `name` and dominated the payload
- Reference datasets are cached in-process for 24 hours, so repeated lookups cost one download instead of one per call
- `trip_class` is normalized before use: an unsupported value falls back to economy and the response echoes `economy` rather than the bogus input
- `price_note` now warns explicitly when a non-economy class was requested that the cached prices are still economy fares
- Dev dependencies moved to current majors: pytest 9, pytest-asyncio 1.x, pytest-cov 7

### Added
- Optional streamable-HTTP transport: set `MCP_PORT` (or `PORT`) to serve over HTTP instead of stdio, with `MCP_HOST` to control the bind address. Ported from [@vovayartsev](https://github.com/vovayartsev)'s fork, re-implemented with constant-time token comparison, `Authorization: Bearer` support and config via pydantic-settings
- `MCP_AUTH_TOKEN` shared-secret auth for the HTTP transport. The token goes in an `Authorization: Bearer` header; `?token=` is off by default because uvicorn logs query strings, and needs `MCP_AUTH_ALLOW_QUERY_TOKEN=true`
- Binding a non-loopback address with no token now refuses to start instead of quietly serving an open port; `MCP_ALLOW_INSECURE_HTTP=true` overrides
- GitHub Actions CI: lint + tests on Python 3.12 and 3.13, plus runtime/dev Docker image builds
- `LICENSE` (GPL-3.0), matching the license already declared in `pyproject.toml`
- Retries for transient failures — timeouts, connection errors and 5xx now retry with backoff instead of failing the tool call on the first blip
- A clear error when the API returns non-JSON (e.g. an HTML maintenance page) instead of an unhandled exception
- Test suite grown from 14 to 55 tests (94% coverage): reference lookup/caching, HTTP auth middleware, client retry behaviour, and transport selection

### Removed
- Empty `models/` and `services/` packages that never held any code

### Fixed
- `limit` is clamped at the bottom as well as the top, so `limit=0` or a negative value no longer reaches the API
- Party sizes are now clamped to combinations Aviasales actually accepts (`adults + children <= 9`, `infants <= adults`). Previously a request like 9 adults + 2 children produced a link that Aviasales silently reset to a single passenger — the link looked fine and was wrong
- A persistent 429 during a reference lookup no longer escapes as an unhandled `RateLimitError`; it returns an error dict like every other failure. `RateLimitError` is not an `ApiError`, and the lookup path only caught the latter
- A `Retry-After` of `NaN` crashed `asyncio.sleep`, and `inf` would have parked the call forever. The delay is now required to be finite and capped at 30s
- Reference lookups fall back to the stale cached dataset when a refresh fails, instead of failing outright

## 2026-07-12

### Added
- Passenger parameters for `search_flights`, `get_prices_calendar` and `get_latest_prices`: `adults` (1-9), `children` (0-8), `infants` (0-8) and `trip_class` (economy/comfort/business/first)
- Passenger party and trip class are encoded into `booking_link`, so the link opens Aviasales with the full party pre-filled
- `passengers`, `trip_class` and `price_note` fields in tool responses (cached prices are always per adult)
- Tests for passenger-block encoding and booking-link rewriting
- `duration_total` and `layover_minutes` fields on tickets: full door-to-door time and combined ground time between connecting flights (derived as duration − flight time)

## 2026-03-17

### Added
- Initial implementation of Aviasales MCP server
- Flight search tools: `search_flights`, `get_prices_calendar`, `get_latest_prices`, `get_popular_directions`, `get_alternative_directions`
- Reference data tools: `lookup_airlines`, `lookup_airports`, `lookup_cities`, `lookup_countries`
- Travelpayouts API v3 client with retry on 429 and error handling
- Configuration via pydantic-settings (AVIASALES_API_TOKEN, AVIASALES_PARTNER_ID)
- Multi-stage Dockerfile (runtime + dev)
- Tests with respx mocks (6 tests)
- README with setup and MCP client config
