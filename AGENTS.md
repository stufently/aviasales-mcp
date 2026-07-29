# AGENTS.md

Working notes for agents on this repo. Usage and configuration live in
`README.md`; what changed and when lives in `CHANGELOG.md`; open work lives in
`TASKS.md`. Don't restate any of that here.

## Layout

```
src/aviasales_mcp/
  server.py          entry point: builds the FastMCP app, registers tools with
                     read-only annotations, picks stdio vs streamable-http
  config.py          pydantic-settings Settings (single `settings` instance)
  auth.py            TokenAuthMiddleware — HTTP transport only
  validation.py      argument validation; raises InvalidArgumentError
  api/client.py      the one place that talks to api.travelpayouts.com
  tools/responses.py the `guard` decorator + error payload contract
  tools/flights.py   price search tools + Aviasales deep-link building
  tools/reference.py airline/airport/city/country lookups, dataset cache,
                     nearest-airport search
tests/               respx-mocked; no network, no token needed
```

## Conventions

- Everything goes through `api/client.py`. It owns retries (429, 5xx, timeouts,
  connection errors), the pooled `AsyncClient`, the `X-Access-Token` header and
  error translation into `ApiError` / `RateLimitError`. Don't call `httpx` from a
  tool module.
- Tool functions return plain dicts and never raise. Wrap every one in
  `@guard(<module error builder>)` rather than writing try/except by hand: it
  turns `InvalidArgumentError` and `TravelpayoutsError` into error payloads and
  logs anything else instead of echoing its text. An exception escaping a tool
  surfaces to the model as a protocol error rather than something it can act on.
- Validate arguments in `validation.py` *before* the API call. Travelpayouts
  answers a bad code or date with an empty list, which a model reads as "no
  flights on this route".
- Every response carries `status`; errors and empty results carry a `hint`
  naming the next tool or parameter to try.
- Tool docstrings are the model's only documentation — they are what ends up in
  the MCP tool schema. Keep the `Args:`/`Returns:` sections accurate, and
  cross-reference sibling tools ("for X use Y instead"). Put bounds and enums in
  the signature (`Annotated[int, Field(ge=…)]`, `Literal[…]`) so they reach the
  schema instead of being clamped invisibly.
- Bump the version in `pyproject.toml` when tool descriptions or the tool list
  change: clients cache tool definitions and key the cache on the server version.
- Never return an unbounded dataset to the caller. The reference endpoints are
  megabytes; that is what `search`/`limit`/`truncated` exist for.
- Logging goes to stderr. stdout is the MCP stdio transport — a stray `print`
  corrupts the protocol.

## Build and test

Nothing is installed on the host — use Docker:

```bash
docker build --target dev -t aviasales-mcp-dev .
docker run --rm aviasales-mcp-dev pytest -q
docker run --rm -v "$(pwd)":/app -w /app aviasales-mcp-dev ruff check src/ tests/
```

## Gotchas

- **`/aviasales/v3/get_latest_prices` answers in the v2 shape** despite its path:
  `value`/`gate`/`depart_date`/`number_of_changes`, no `link`. Parsing it as v3
  silently produced empty tickets for months. Check a new endpoint's actual rows
  before picking a formatter — the path version does not tell you.
- **`gate` is the selling agency** ("Kupi.com", "Aviakassa", "Biletix"), not an
  airline. The v2 rows carry no airline at all.
- **`/aviasales/v3/get_popular_directions` is keyed on `destination`** and returns
  the origins people fly from; passing only `origin` is a 400. "Where can I fly
  from X" is `/v1/city-directions`.
- **The price cache is per market.** LON→NYC in USD comes back 331 for
  `market=ru` and 317 for `market=us`. Unset means the ru cache.
- **Rate limits differ per endpoint**: 600/min for most v3 paths, 300/min for
  latest prices and month-matrix, **60/min** for week-matrix and
  nearest-places-matrix. The client warns when the published budget runs low.
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
