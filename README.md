# aviasales-mcp

MCP server for flight price search via Aviasales / Travelpayouts Data API.

## Tools

| Tool | Description |
|------|-------------|
| `search_flights` | Search flight prices between two cities (v3/prices_for_dates) |
| `get_prices_calendar` | Grouped prices by date — find the cheapest day to fly |
| `get_latest_prices` | Most recently found flight prices |
| `get_popular_directions` | Popular destinations from a city |
| `get_alternative_directions` | Prices for nearby airports/cities |
| `lookup_airlines` | List of all airlines with IATA codes |
| `lookup_airports` | List of all airports |
| `lookup_cities` | List of all cities with IATA codes |
| `lookup_countries` | List of all countries |

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

## Development

```bash
docker build --target dev -t aviasales-mcp-dev .
docker run --rm aviasales-mcp-dev pytest
docker run --rm aviasales-mcp-dev ruff check src/
```
