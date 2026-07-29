# AGENTS.md

Working notes for agents on this repo. Usage and configuration live in
`README.md`; what changed and when lives in `CHANGELOG.md`; open work lives in
`TASKS.md`. Don't restate any of that here.

## Layout

```
src/aviasales_mcp/
  server.py          entry point: builds the FastMCP app, registers tools,
                     picks stdio vs streamable-http
  config.py          pydantic-settings Settings (single `settings` instance)
  auth.py            TokenAuthMiddleware — HTTP transport only
  api/client.py      the one place that talks to api.travelpayouts.com
  tools/flights.py   price search tools + Aviasales deep-link building
  tools/reference.py airline/airport/city/country lookups + dataset cache
tests/               respx-mocked; no network, no token needed
```

## Conventions

- Everything goes through `api/client.py`. It owns retries (429, 5xx, timeouts,
  connection errors), the `X-Access-Token` header and error translation into
  `ApiError` / `RateLimitError`. Don't call `httpx` from a tool module.
- Tool functions return plain dicts and never raise: catch `TravelpayoutsError`
  (the base class — `RateLimitError` is *not* an `ApiError`) and return an error
  dict. An exception escaping a tool surfaces to the model as a protocol error
  rather than something it can act on.
- Tool docstrings are the model's only documentation — they are what ends up in
  the MCP tool schema. Keep the `Args:`/`Returns:` sections accurate.
- Never return an unbounded dataset to the caller. The reference endpoints are
  megabytes; that is what `search`/`limit`/`truncated` exist for.

## Build and test

Nothing is installed on the host — use Docker:

```bash
docker build --target dev -t aviasales-mcp-dev .
docker run --rm aviasales-mcp-dev pytest -q
docker run --rm -v "$(pwd)":/app -w /app aviasales-mcp-dev ruff check src/ tests/
```

## Gotchas

- **The Data API ignores `trip_class` and has no passenger parameters.** Verified
  live: identical payloads and identical `link` values with and without it. The
  party is encoded into the booking deep link instead, and the prices stay
  per-adult economy no matter what was requested.
- **Aviasales deep-link passenger block is class-letter-first**: `c21` is
  business / 2 adults / 1 child. `21c` is parsed as a single passenger, so the
  ordering is not cosmetic. Trailing zeros are stripped (`100` → `1`).
- **An invalid party silently degrades to one passenger** rather than erroring:
  `/search/MOW2509BKK92` (9 adults + 2 children) renders as "1 пассажир". So
  `adults + children <= 9` and `infants <= adults` have to be enforced in
  `_clamp_party` before the link is built, or the link quietly lies.
- `duration` from the v3 API is door-to-door, while `duration_to`/`duration_back`
  are pure flight time — the difference is the layover, which is where
  `layover_minutes` comes from.
- `config.py` builds `settings` at import time, so tests must set
  `AVIASALES_API_TOKEN` before importing anything from `aviasales_mcp` (see
  `tests/conftest.py`).
- The reference dataset cache is process-global; `reference._reset_cache()` keeps
  it from leaking between tests (autouse fixture in `conftest.py`).
