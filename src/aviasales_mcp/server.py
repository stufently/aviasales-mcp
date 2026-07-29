"""Aviasales MCP Server — entry point."""

from __future__ import annotations

import logging

from fastmcp import FastMCP
from starlette.middleware import Middleware

from aviasales_mcp.auth import TokenAuthMiddleware
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

logger = logging.getLogger(__name__)

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


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def main() -> None:
    port = settings.mcp_port
    if port is None:
        mcp.run(transport="stdio")
        return

    host = settings.mcp_host
    token = settings.mcp_auth_token

    middleware = None
    if token:
        middleware = [
            Middleware(
                TokenAuthMiddleware,
                token=token.get_secret_value(),
                allow_query_token=settings.mcp_auth_allow_query_token,
            )
        ]
    elif host in _LOOPBACK_HOSTS or settings.mcp_allow_insecure_http:
        logger.warning(
            "Serving HTTP on %s:%d without MCP_AUTH_TOKEN — anyone who can reach this "
            "port can spend your Travelpayouts quota.",
            host,
            port,
        )
    else:
        # Binding a public interface with no auth hands the API token to whoever
        # finds the port, so refuse rather than warn and carry on.
        raise SystemExit(
            f"Refusing to serve HTTP on {host}:{port} without MCP_AUTH_TOKEN. "
            "Set MCP_AUTH_TOKEN, bind MCP_HOST to loopback, or set "
            "MCP_ALLOW_INSECURE_HTTP=true if this port is genuinely private."
        )

    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        middleware=middleware,
    )


if __name__ == "__main__":
    main()
