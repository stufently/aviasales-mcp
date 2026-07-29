# aviasales-mcp

MCP server for flight price search via Aviasales / Travelpayouts Data API.

## Tools

### Flight prices

| Tool | Description |
|------|-------------|
| `search_flights` | Search flight prices between two cities (v3/prices_for_dates) |
| `get_prices_calendar` | Grouped prices by date — find the cheapest day to fly |
| `get_latest_prices` | Most recently found flight prices |
| `get_popular_directions` | Popular destinations from a city |
| `get_alternative_directions` | Prices for nearby airports/cities |

`search_flights`, `get_prices_calendar` and `get_latest_prices` accept `adults`
(1–9), `children` (0–8), `infants` (0–8) and `trip_class`
(`economy`/`comfort`/`business`/`first`).

The Data API serves a cache of recent searches and takes no passenger
parameters, so the party is encoded into each ticket's `booking_link` instead —
the link opens Aviasales with the full party and class pre-filled and shows the
real total. **The prices themselves are always per adult in economy**, which is
what the `price_note` field in every response spells out for the model.

Tickets also carry `duration_total` (door-to-door minutes), `duration_to` /
`duration_back` (flight time per direction) and `layover_minutes` (combined
ground time between connections).

### Reference data

| Tool | Description |
|------|-------------|
| `lookup_airlines` | Airlines by name or IATA code |
| `lookup_airports` | Airports by name, IATA code, or city code |
| `lookup_cities` | Cities by name or IATA code — turn a city name into a code |
| `lookup_countries` | Countries by name or code |

Each takes `search` and `limit` (default 50, max 500) and returns
`{total, returned, truncated, data}`. Always pass `search`: the underlying
datasets are ~10k airports and ~9.6k cities, which is far more than any model
can hold in context. Each dataset is downloaded once per process and cached for
24 hours.

## Setup

1. Get an API token at https://www.travelpayouts.com/programs/100/tools/api
2. Copy `.env.example` to `.env` and fill in your token
3. Build and run with Docker:

```bash
docker build -t aviasales-mcp .
docker run --env-file .env aviasales-mcp
```

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `AVIASALES_API_TOKEN` | Yes | Travelpayouts API token |
| `AVIASALES_PARTNER_ID` | No | Partner ID for booking links |
| `LOG_LEVEL` | No | Logging level (default: INFO) |
| `MCP_PORT` | No | Serve streamable-HTTP on this port instead of stdio (`PORT` also accepted) |
| `MCP_HOST` | No | Bind address for HTTP mode (default: `127.0.0.1`; use `0.0.0.0` in Docker) |
| `MCP_AUTH_TOKEN` | No | Shared secret required on every HTTP request |
| `MCP_AUTH_ALLOW_QUERY_TOKEN` | No | Also accept the token as `?token=` (default: false) |
| `MCP_ALLOW_INSECURE_HTTP` | No | Permit a non-loopback bind with no token (default: false) |

## MCP client config

```json
{
  "mcpServers": {
    "aviasales": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--env-file", "/path/to/.env", "aviasales-mcp"]
    }
  }
}
```

## HTTP transport

By default the server speaks stdio, which is what local MCP clients expect.
Setting `MCP_PORT` switches it to streamable-HTTP so it can be reached remotely:

```bash
docker run --env-file .env \
  -e MCP_PORT=8080 -e MCP_HOST=0.0.0.0 -e MCP_AUTH_TOKEN=<your-secret> \
  -p 8080:8080 aviasales-mcp
```

The endpoint is then `http://<host>:8080/mcp`, and every request must present
the token as `Authorization: Bearer <token>`; anything else gets a 401.

Some MCP clients cannot set headers. `MCP_AUTH_ALLOW_QUERY_TOKEN=true` also
accepts `?token=<token>`, but note that uvicorn — and any proxy in front of it —
writes the full URL to its access log, so the secret ends up in logs. Prefer the
header.

There is no TLS here: terminate it at a reverse proxy if the port is reachable
from anywhere untrusted.

Without `MCP_AUTH_TOKEN` the port is unauthenticated and anyone who reaches it
can spend your Travelpayouts quota. Loopback binds are allowed (with a warning);
binding anything else refuses to start unless you also set
`MCP_ALLOW_INSECURE_HTTP=true`.

## Development

```bash
docker build --target dev -t aviasales-mcp-dev .
docker run --rm aviasales-mcp-dev pytest -q
docker run --rm -v "$(pwd)":/app -w /app aviasales-mcp-dev ruff check src/ tests/
```

CI runs the suite on Python 3.12 and 3.13 plus a Docker image build — see
`.github/workflows/ci.yml`.

## License

GPL-3.0-or-later — see [LICENSE](LICENSE).
