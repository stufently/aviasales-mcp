# Tasks

## Active

- [ ] **Publish to PyPI** (owner — needs the account and an API token, or a
      trusted publisher configured on pypi.org). Packaging is done and verified:
      `python -m build` produces both artifacts and `twine check` passes on each,
      and README already carries the `mcp-name:` marker the MCP registry checks on
      PyPI. Remaining steps are all credentialed — claim the `aviasales-mcp` name,
      `twine upload dist/*` (or a trusted-publisher GitHub Action), then add a
      `"registryType": "pypi"` package to `server.json` beside the OCI one and
      re-run the `MCP Registry` workflow with a bumped version. Until then the
      README's `uvx` mention stays conditional
- [ ] Real-time search (`/v1/flight_search` + `/v1/flight_search_results`, MD5
      signature, separate product needing approval). This is the only way to drop
      the "prices are a 48h cache" caveat the whole `price_note` machinery exists
      to apologise for. Pair it with a `search_id` → filter → detail tool split so
      results do not flood the context
- [ ] `/aviasales/v3/autocomplete?term=&types=city|airport` — server-side place
      lookup that could replace the 2.5 MB `airports.json` download for the common
      "city name → IATA" path
- [ ] `/aviasales/v3/get_special_offers` — airline promo fares (alive, 600/min)
- [ ] `min_trip_duration` / `max_trip_duration` on `get_prices_calendar` — serves
      "a 10-14 day trip in September" (verified working live)
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
| 11 | Competitor + API-surface audit; fixed latest-prices/popular-directions/agency/market defects, added 4 tools | 2026-07-29 |
| 12 | PyPI-ready packaging (urls, license-files, py.typed, classifiers), README install + client configs, repo description and topics | 2026-08-21 |
| 13 | GHCR image + listing in the official MCP registry via GitHub OIDC; README install via Docker for Claude Code, Claude Desktop, Cursor, Windsurf, Zed, Codex | 2026-10-09 |
| 14 | Tool `Use when` descriptions, per-client README JSON, `.mcpb` bundle and tag workflow | 2026-10-10 |
