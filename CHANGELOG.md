# Changelog

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
