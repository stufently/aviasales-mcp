# Changelog

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
