from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from aviasales_mcp.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.travelpayouts.com"
TIMEOUT = 30.0
MAX_RETRIES = 2
RETRY_BACKOFF = 1.0


class TravelpayoutsError(Exception):
    """Base error for Travelpayouts API calls."""


class RateLimitError(TravelpayoutsError):
    """Raised when API returns 429."""


class ApiError(TravelpayoutsError):
    """Raised when API returns an error response."""


async def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    headers = {
        "X-Access-Token": settings.aviasales_api_token.get_secret_value(),
        "Accept-Encoding": "gzip, deflate",
    }
    url = f"{BASE_URL}{path}"

    for attempt in range(MAX_RETRIES + 1):
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.request(method, url, params=params, headers=headers)

        if resp.status_code == 429:
            retry_after = float(resp.headers.get("Retry-After", RETRY_BACKOFF))
            if attempt < MAX_RETRIES:
                logger.warning(
                    "Rate limited, retrying in %.1fs (attempt %d)", retry_after, attempt + 1
                )
                await asyncio.sleep(retry_after)
                continue
            raise RateLimitError("Rate limit exceeded, all retries exhausted")

        if resp.status_code == 401:
            raise ApiError("Unauthorized — check AVIASALES_API_TOKEN")

        if resp.status_code != 200:
            raise ApiError(f"HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json()

        if isinstance(data, dict) and data.get("success") is False:
            raise ApiError(f"API error: {data.get('error', 'unknown error')}")

        return data

    raise ApiError("Unexpected retry loop exit")


async def get(path: str, **params: Any) -> Any:
    clean = {k: v for k, v in params.items() if v is not None}
    return await _request("GET", path, params=clean)
