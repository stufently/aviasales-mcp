"""MCP tools for reference/lookup data (airlines, airports, cities)."""

from __future__ import annotations

from aviasales_mcp.api.client import ApiError, get


async def lookup_airlines() -> list[dict]:
    """Get the list of all airlines with IATA codes.

    Returns:
        List of airline objects with name, iata, icao, is_lowcost fields.
    """
    try:
        data = await get("/data/en/airlines.json")
        return data if isinstance(data, list) else []
    except ApiError as e:
        return [{"error": str(e)}]


async def lookup_airports() -> list[dict]:
    """Get the list of all airports with IATA codes, cities, and coordinates.

    Returns:
        List of airport objects.
    """
    try:
        data = await get("/data/en/airports.json")
        return data if isinstance(data, list) else []
    except ApiError as e:
        return [{"error": str(e)}]


async def lookup_cities() -> list[dict]:
    """Get the list of all cities with IATA codes and country codes.

    Returns:
        List of city objects.
    """
    try:
        data = await get("/data/en/cities.json")
        return data if isinstance(data, list) else []
    except ApiError as e:
        return [{"error": str(e)}]


async def lookup_countries() -> list[dict]:
    """Get the list of all countries with codes and currency info.

    Returns:
        List of country objects.
    """
    try:
        data = await get("/data/en/countries.json")
        return data if isinstance(data, list) else []
    except ApiError as e:
        return [{"error": str(e)}]
