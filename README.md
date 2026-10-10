# aviasales-mcp

<!-- mcp-name: io.github.stufently/aviasales-mcp -->

MCP server for flight price search via Aviasales / Travelpayouts Data API.
Thirteen read-only tools that let Claude Code, Claude Desktop, Cursor or any
other MCP client answer flight-price questions: fares by route and month, the
cheapest day to fly, flexible dates, budget and inspiration search, plus
airport/city/airline lookup.

Unlike Google-Flights-scraping MCP servers, place names do not have to be
guessed into IATA codes by the model: `lookup_cities` and `find_nearest_airports`
resolve them.

## Example prompts

Ask in plain language. The server picks the tool.

- How much is a flight from Moscow to Istanbul in March?
- What is the cheapest day to fly to Bangkok in September?
- I am flying Berlin to Lisbon on 12 May and back on the 19th. Would shifting a day either way be cheaper?
- Where can I fly from St Petersburg for under 30 000 rubles?
- Which airport should I fly into for Pattaya, and what does it cost from Dubai?

## Common prompts

The same kind of question, with the tools a typical agent reaches for.

| Prompt | Tools it reaches for |
|--------|----------------------|
| "How much is a flight from Moscow to Istanbul in March?" | `lookup_cities` → `search_flights` |
| "What's the cheapest day to fly to Bangkok in September?" | `get_prices_calendar` |
| "I'm flying Berlin→Lisbon on 12 May, back on the 19th — would shifting a day either way be cheaper?" | `get_flexible_date_prices` |
| "Where can I fly from St Petersburg for under 30 000 ₽?" | `get_city_directions`, `search_by_price_range` |
| "Which airport should I fly into for Pattaya, and what does it cost from Dubai?" | `find_nearest_airports` → `search_flights` |
| "Evening departures only, two adults and a child, business class." | `search_flights` with `depart_after`, `adults`, `children`, `trip_class` |

## Install

Paste this into a terminal. It is the same `docker` command every client block
below runs; the process speaks MCP on stdin and waits there.

```bash
AVIASALES_API_TOKEN=your-token-here AVIASALES_MARKET=ru \
  docker run -i --rm \
  -e AVIASALES_API_TOKEN \
  -e AVIASALES_MARKET \
  ghcr.io/stufently/aviasales-mcp:latest
```

You need Docker, and a free Travelpayouts API token from
<https://www.travelpayouts.com/programs/100/tools/api>. A wrong token still
lets the process start; it surfaces as an error on the first search.
`AVIASALES_MARKET` is optional — see [Configuration](#configuration). Drop
that variable and its `-e` pair if you do not need it.

`:latest` follows releases; pin a version tag (`:0.5.1`) if you would rather
upgrade by hand. The package is PyPI-ready, and it is not on PyPI: `uvx
aviasales-mcp` does nothing useful until a release is uploaded. Until then
the command above is the install path.

## MCP client configs

Every block runs the same `docker` command as the terminal snippet above.
`-e AVIASALES_API_TOKEN` with no value hands the container the variable the
client sets in `env`, so the token is written in exactly one place.

> **Keep the token out of anything you commit.** A project-level `.mcp.json`,
> `.cursor/mcp.json` or `.zed/settings.json` is a normal thing to check into git,
> and a token pasted there goes with it. Prefer the user-level config file, or
> `.gitignore` the project one.

### Claude Code

Project file: `.mcp.json` in the project root.

```json
{
  "mcpServers": {
    "aviasales": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "AVIASALES_API_TOKEN",
        "-e", "AVIASALES_MARKET",
        "ghcr.io/stufently/aviasales-mcp:latest"
      ],
      "env": {
        "AVIASALES_API_TOKEN": "your-token-here",
        "AVIASALES_MARKET": "ru"
      }
    }
  }
}
```

Or from the terminal:

```bash
claude mcp add --scope user aviasales \
  -e AVIASALES_API_TOKEN=your-token-here -e AVIASALES_MARKET=ru -- \
  docker run -i --rm -e AVIASALES_API_TOKEN -e AVIASALES_MARKET \
  ghcr.io/stufently/aviasales-mcp:latest
```

`--scope user` makes it available in every project and keeps the token in
`~/.claude.json`, out of the repository. Check with `claude mcp list`.

### Claude Desktop

File: `claude_desktop_config.json` — macOS
`~/Library/Application Support/Claude/claude_desktop_config.json`, Windows
`%APPDATA%\Claude\claude_desktop_config.json`, Linux
`~/.config/Claude/claude_desktop_config.json`.

```json
{
  "mcpServers": {
    "aviasales": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "AVIASALES_API_TOKEN",
        "-e", "AVIASALES_MARKET",
        "ghcr.io/stufently/aviasales-mcp:latest"
      ],
      "env": {
        "AVIASALES_API_TOKEN": "your-token-here",
        "AVIASALES_MARKET": "ru"
      }
    }
  }
}
```

One click, without editing JSON: download the `.mcpb` from
https://github.com/stufently/aviasales-mcp/releases/latest and open it.
Claude Desktop installs the extension and asks for the Travelpayouts API token.

Claude Desktop starts with a trimmed `PATH` and may not find `docker` by name: if
the server fails to start, replace `"docker"` with its absolute path
(`which docker`).

### Cursor

File: `~/.cursor/mcp.json` (every project) or `.cursor/mcp.json` (this project).

```json
{
  "mcpServers": {
    "aviasales": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "AVIASALES_API_TOKEN",
        "-e", "AVIASALES_MARKET",
        "ghcr.io/stufently/aviasales-mcp:latest"
      ],
      "env": {
        "AVIASALES_API_TOKEN": "your-token-here",
        "AVIASALES_MARKET": "ru"
      }
    }
  }
}
```

### Windsurf

File: `mcp_config.json` — macOS and Linux `~/.config/devin/mcp_config.json`
(or `$XDG_CONFIG_HOME/devin/mcp_config.json`), Windows
`%APPDATA%\devin\mcp_config.json`. Older builds read
`~/.codeium/windsurf/mcp_config.json`.

```json
{
  "mcpServers": {
    "aviasales": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "AVIASALES_API_TOKEN",
        "-e", "AVIASALES_MARKET",
        "ghcr.io/stufently/aviasales-mcp:latest"
      ],
      "env": {
        "AVIASALES_API_TOKEN": "your-token-here",
        "AVIASALES_MARKET": "ru"
      }
    }
  }
}
```

### Zed

File: `settings.json` at `~/.config/zed/settings.json` (or **zed: open settings**).

```json
{
  "context_servers": {
    "aviasales": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "AVIASALES_API_TOKEN",
        "-e", "AVIASALES_MARKET",
        "ghcr.io/stufently/aviasales-mcp:latest"
      ],
      "env": {
        "AVIASALES_API_TOKEN": "your-token-here",
        "AVIASALES_MARKET": "ru"
      }
    }
  }
}
```

### Codex

```bash
codex mcp add aviasales --env AVIASALES_API_TOKEN=your-token-here -- \
  docker run -i --rm -e AVIASALES_API_TOKEN ghcr.io/stufently/aviasales-mcp:latest
```

Or by hand in `~/.codex/config.toml`:

```toml
[mcp_servers.aviasales]
command = "docker"
args = ["run", "-i", "--rm", "-e", "AVIASALES_API_TOKEN", "-e", "AVIASALES_MARKET",
        "ghcr.io/stufently/aviasales-mcp:latest"]

[mcp_servers.aviasales.env]
AVIASALES_API_TOKEN = "your-token-here"
AVIASALES_MARKET = "ru"
```

### Any other stdio client

Command `docker`, arguments
`run -i --rm -e AVIASALES_API_TOKEN ghcr.io/stufently/aviasales-mcp:latest`, and
`AVIASALES_API_TOKEN` in the environment the client gives the process. The
server is also listed in the official MCP registry as
`io.github.stufently/aviasales-mcp`, which clients with a registry browser can
install from directly.

## Tools

### Flight prices

| Tool | Description |
|------|-------------|
| `search_flights` | Prices between two cities on a date or across a month (v3/prices_for_dates) |
| `get_prices_calendar` | Prices grouped by day or month — the cheapest day to fly |
| `get_flexible_date_prices` | Prices for the days around your dates — "would shifting a day be cheaper?" |
| `get_latest_prices` | Most recently found fares, optionally filtered by route |
| `get_popular_directions` | Where travellers reach a destination **from** |
| `get_city_directions` | Cheapest destinations reachable **from** a city — inspiration search |
| `get_alternative_directions` | Prices for nearby airports/cities |
| `search_by_price_range` | Flights inside a budget; omit the destination to search anywhere (no date filter — the endpoint ignores one) |

`search_flights`, `get_prices_calendar`, `get_flexible_date_prices` and
`get_latest_prices` accept `adults` (1–9), `children` (0–8), `infants` (0–8) and
`trip_class` (`economy`/`comfort`/`business`/`first`).

The Data API serves a cache of recent searches and takes no passenger
parameters, so the party is encoded into each ticket's `booking_link` instead —
the link opens Aviasales with the full party and class pre-filled and shows the
real total. **The prices themselves are always per adult in economy**, which is
what the `price_note` field on every price response spells out for the model.

`search_flights` also takes `depart_after` / `depart_before` (`HH:MM`, 24-hour)
to keep only departures in a time window; set `depart_after` later than
`depart_before` for a window that wraps midnight (red-eyes).

Tickets carry `duration_total` (door-to-door minutes), `duration_to` /
`duration_back` (flight time per direction) and `layover_minutes` (combined
ground time between connections). Every price response also carries a
`price_summary` (min/median/max) so the model can tell a good fare from a bad one
without a second search.

### Reference data

| Tool | Description |
|------|-------------|
| `lookup_airlines` | Airlines by name or IATA code |
| `lookup_airports` | Airports by name, IATA code, or city code |
| `lookup_cities` | Cities by name or IATA code — turn a city name into a code |
| `lookup_countries` | Countries by name or code |
| `find_nearest_airports` | Airports closest to a place or to lat/lon, by distance |

The `lookup_*` tools take `search`, `limit` (default 50, max 500) and `locale`,
and return `{status, total, returned, truncated, data}`. Always pass `search`:
the underlying datasets are ~10k airports and ~9.6k cities, which is far more
than any model can hold in context. Matches are ranked (exact code, then exact
city code, then name), and airports with no scheduled service sort last. Each
dataset is downloaded once per process and cached for 24 hours.

`find_nearest_airports` answers the question `lookup_airports` cannot: the
closest airport is rarely named after the town. It resolves `near="Pattaya"`
against the cached city and airport datasets and ranks by great-circle distance —
no third-party geocoder involved.

### Errors and empty results

Every response carries `status` (`"ok"` or `"error"`), so an empty `data` list is
never confused with a failure. Bad input is refused before the API call, with the
expected format spelled out (`"departure_at must be \"YYYY-MM-DD\" or
\"YYYY-MM\"…"`), and both error and empty responses carry a `hint` naming what to
try next. On a rejected argument the hint says what to substitute and which tool
resolves it — enough for the model to fix the call itself on the second attempt.

## Setup

Building the image yourself from a checkout, instead of pulling it:

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
| `AVIASALES_DEFAULT_CURRENCY` | No | Default price currency (default: `rub`) |
| `AVIASALES_MARKET` | No | 2-letter market whose price cache to read (unset → `ru`) |
| `AVIASALES_LOCALE` | No | Language of reference data names (default: `en`) |
| `LOG_LEVEL` | No | Logging level (default: INFO) |
| `MCP_PORT` | No | Serve streamable-HTTP on this port instead of stdio (`PORT` also accepted) |
| `MCP_HOST` | No | Bind address for HTTP mode (default: `127.0.0.1`; use `0.0.0.0` in Docker) |
| `MCP_AUTH_TOKEN` | No | Shared secret required on every HTTP request |
| `MCP_AUTH_ALLOW_QUERY_TOKEN` | No | Also accept the token as `?token=` (default: false) |
| `MCP_ALLOW_INSECURE_HTTP` | No | Permit a non-loopback bind with no token (default: false) |

`AVIASALES_MARKET` is worth setting: the price cache is per market, and the same
route in the same currency comes back at a different price for `ru` and `us`.

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

## Limitations

- **Prices are a cache of recent searches**, not live availability. A fare can be
  gone by the time the link opens; `expires_at` says when the quote lapses.
- **Prices are always per adult in economy.** Passenger count and cabin change
  the booking link, never the quoted number.
- **No booking.** This server searches and links out; it never holds or buys.
- **Cache coverage is uneven.** An empty result means nobody searched that route
  recently, not that the route does not exist.
- **`get_latest_prices`, the matrices and nearby airports** come from the older
  v2 response shape: they name the selling `agency` rather than the airline and
  carry no flight number.
- **Rate limits are per endpoint** (600/min for most, 60/min for the week and
  nearby matrices). The server retries 429s and warns when the published quota
  runs low.

## Development

```bash
docker build --target dev -t aviasales-mcp-dev .
docker run --rm aviasales-mcp-dev pytest -q
docker run --rm -v "$(pwd)":/app -w /app aviasales-mcp-dev ruff check src/ tests/
```

CI runs the suite on Python 3.12, 3.13 and 3.14 plus a Docker image build — see
`.github/workflows/ci.yml`.

## License

GPL-3.0-or-later — see [LICENSE](LICENSE).
