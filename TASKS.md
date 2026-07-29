# Tasks

## Active

- [ ] Add GraphQL endpoint support (aviasales GraphQL API)
- [ ] Add hotel search tools (Hotellook API)
- [ ] Add integration tests against the real API (currently everything is respx-mocked)

## Completed

| # | Task | Date |
|---|------|------|
| 1 | Implement MCP server with flight search tools (v3 API) | 2026-03-17 |
| 2 | Add reference data tools (airlines, airports, cities, countries) | 2026-03-17 |
| 3 | Add tests with respx mocks | 2026-03-17 |
| 4 | Multi-stage Dockerfile | 2026-03-17 |
| 5 | Rename AVIASALES_MARKER → AVIASALES_PARTNER_ID | 2026-03-17 |
| 6 | Passenger + trip class params encoded into booking links (PR #1) | 2026-07-12 |
| 7 | Verify API token — confirmed working, the old 401 is gone | 2026-07-29 |
| 8 | Make `lookup_*` usable: search/limit/caching instead of dumping whole datasets | 2026-07-29 |
| 9 | Optional streamable-HTTP transport with token auth | 2026-07-29 |
| 10 | CI/CD pipeline (GitHub Actions: lint, tests on 3.12/3.13, Docker build) | 2026-07-29 |
