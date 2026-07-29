from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

import httpx

from aviasales_mcp.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.travelpayouts.com"
TIMEOUT = 30.0
MAX_RETRIES = 2
RETRY_BACKOFF = 1.0
# A hostile or broken Retry-After must not be able to park a tool call forever.
MAX_RETRY_DELAY = 30.0


class TravelpayoutsError(Exception):
    """Base error for Travelpayouts API calls."""


class RateLimitError(TravelpayoutsError):
    """Raised when API returns 429."""


class ApiError(TravelpayoutsError):
    """Raised when API returns an error response."""


def _retry_after(resp: httpx.Response) -> float:
    """Seconds to wait per the Retry-After header, bounded to something sane."""
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return RETRY_BACKOFF
    try:
        delay = float(raw)
    except (ValueError, TypeError):
        # Retry-After is allowed to be an HTTP-date; rather than guess at the
        # clock skew, fall back to the usual backoff.
        return RETRY_BACKOFF
    # NaN slips through float() and then blows up asyncio.sleep; inf would hang.
    if not math.isfinite(delay):
        return RETRY_BACKOFF
    return max(0.0, min(delay, MAX_RETRY_DELAY))


async def _backoff(attempt: int, reason: str) -> None:
    delay = RETRY_BACKOFF * (attempt + 1)
    logger.warning("Retrying after %s in %.1fs (attempt %d)", reason, delay, attempt + 1)
    await asyncio.sleep(delay)


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
        final_attempt = attempt == MAX_RETRIES

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.request(method, url, params=params, headers=headers)
        except httpx.TimeoutException:
            if final_attempt:
                raise ApiError("Request timed out")
            await _backoff(attempt, "timeout")
            continue
        except httpx.HTTPError as exc:
            if final_attempt:
                raise ApiError(f"Connection error: {exc}")
            await _backoff(attempt, f"connection error: {exc}")
            continue

        if resp.status_code == 429:
            if final_attempt:
                raise RateLimitError("Rate limit exceeded, all retries exhausted")
            retry_after = _retry_after(resp)
            logger.warning("Rate limited, retrying in %.1fs (attempt %d)", retry_after, attempt + 1)
            await asyncio.sleep(retry_after)
            continue

        if resp.status_code == 401:
            raise ApiError("Unauthorized — check AVIASALES_API_TOKEN")

        # 5xx is normally a transient upstream blip, so it is worth another go.
        if resp.status_code >= 500:
            if final_attempt:
                raise ApiError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            await _backoff(attempt, f"HTTP {resp.status_code}")
            continue

        if resp.status_code != 200:
            raise ApiError(f"HTTP {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
        except ValueError:
            raise ApiError("API returned a non-JSON response")

        if isinstance(data, dict) and data.get("success") is False:
            raise ApiError(f"API error: {data.get('error', 'unknown error')}")

        return data

    raise ApiError("Unexpected retry loop exit")


async def get(path: str, **params: Any) -> Any:
    clean = {k: v for k, v in params.items() if v is not None}
    return await _request("GET", path, params=clean)
