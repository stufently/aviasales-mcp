"""Aviasales MCP Server — entry point."""

from __future__ import annotations

import logging

from fastmcp import FastMCP

from aviasales_mcp.config import settings
from aviasales_mcp.tools.flights import (
    get_alternative_directions,
    get_latest_prices,
    get_popular_directions,
    get_prices_calendar,
    search_flights,
)
from aviasales_mcp.tools.reference import (
    lookup_airlines,
    lookup_airports,
    lookup_cities,
    lookup_countries,
)

logging.basicConfig(level=settings.log_level.upper(), format="%(levelname)s %(name)s: %(message)s")

mcp = FastMCP(
    "Aviasales",
    instructions=(
        "Flight search assistant powered by Aviasales/Travelpayouts API. "
        "Use the tools to search flight prices, find cheapest dates, "
        "discover popular directions, and look up airline/airport codes. "
        "All price data comes from the cache of recent user searches (last 48h)."
    ),
)

# Flight tools
mcp.tool()(search_flights)
mcp.tool()(get_prices_calendar)
mcp.tool()(get_latest_prices)
mcp.tool()(get_popular_directions)
mcp.tool()(get_alternative_directions)

# Reference tools
mcp.tool()(lookup_airlines)
mcp.tool()(lookup_airports)
mcp.tool()(lookup_cities)
mcp.tool()(lookup_countries)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
