"""Aviasales MCP Server — entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version

from fastmcp import FastMCP
from starlette.middleware import Middleware

from aviasales_mcp.api import client as api_client
from aviasales_mcp.auth import TokenAuthMiddleware
from aviasales_mcp.config import settings
from aviasales_mcp.tools.flights import (
    get_alternative_directions,
    get_city_directions,
    get_flexible_date_prices,
    get_latest_prices,
    get_popular_directions,
    get_prices_calendar,
    search_by_price_range,
    search_flights,
)
from aviasales_mcp.tools.reference import (
    find_nearest_airports,
    lookup_airlines,
    lookup_airports,
    lookup_cities,
    lookup_countries,
)

logging.basicConfig(level=settings.log_level.upper(), format="%(levelname)s %(name)s: %(message)s")

logger = logging.getLogger(__name__)

try:
    __version__ = version("aviasales-mcp")
except PackageNotFoundError:  # running from a source checkout
    __version__ = "0.0.0.dev0"

@asynccontextmanager
async def _lifespan(_server: FastMCP) -> AsyncIterator[None]:
    """Release the pooled HTTP client when the server stops."""
    try:
        yield
    finally:
        await api_client.aclose()


mcp = FastMCP(
    "Aviasales",
    lifespan=_lifespan,
    # Clients cache tool definitions; without a version they have nothing to
    # invalidate on, so a changed tool description never reaches the model.
    version=__version__,
    instructions=(
        "Flight search assistant powered by Aviasales/Travelpayouts API. "
        "Use the tools to search flight prices, find the cheapest dates, "
        "discover where to fly, and look up airline/airport/city codes. "
        "Every flight tool takes IATA codes — resolve a place name with "
        "lookup_cities or find_nearest_airports first. All price data comes from "
        "a cache of recent user searches (last 48h) and is per adult in economy."
    ),
)

# Every tool is a read-only call against a remote API: nothing is written, the
# same arguments give the same answer, and the data lives outside this server.
_READ_ONLY = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}

_TOOLS = (
    # Flight tools
    search_flights,
    get_prices_calendar,
    get_flexible_date_prices,
    get_latest_prices,
    get_popular_directions,
    get_city_directions,
    get_alternative_directions,
    search_by_price_range,
    # Reference tools
    lookup_airlines,
    lookup_airports,
    lookup_cities,
    lookup_countries,
    find_nearest_airports,
)

for _tool in _TOOLS:
    mcp.tool(annotations=_READ_ONLY)(_tool)


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
