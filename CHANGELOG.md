# Changelog

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
