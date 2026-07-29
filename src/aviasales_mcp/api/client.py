from __future__ import annotations

import asyncio
import logging
import math
import weakref
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
# Travelpayouts publishes the remaining budget on every response; warn before it
# turns into 429s rather than after.
LOW_QUOTA_FRACTION = 0.1

# One pooled client per event loop, so a tool call reuses the connection and TLS
# session instead of paying a fresh handshake every time. Keyed by loop because
# an AsyncClient is bound to the loop it was created on, and the test suite runs
# each test in its own loop. The keys are weak, but that alone does not collect
# anything: an open client keeps its loop alive through the transport, so
# entries for finished loops are dropped explicitly below.
_clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, httpx.AsyncClient] = (
    weakref.WeakKeyDictionary()
)


def _drop_dead_loops() -> None:
    """Forget clients whose event loop is gone; they can never be used again."""
    for loop in [loop for loop in _clients if loop.is_closed()]:
        _clients.pop(loop, None)


def _pooled_client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None or client.is_closed:
        _drop_dead_loops()
        client = httpx.AsyncClient(timeout=TIMEOUT)
        _clients[loop] = client
    return client


async def aclose() -> None:
    """Close the current loop's pooled client, if any.

    Wired into the server lifespan, and called between tests so a suite that
    runs one loop per test does not accumulate open clients.
    """
    loop = asyncio.get_running_loop()
    client = _clients.pop(loop, None)
    if client is not None and not client.is_closed:
        await client.aclose()


def _log_quota(resp: httpx.Response) -> None:
    """Warn when the published rate-limit budget is nearly spent."""
    try:
        limit = int(resp.headers["x-rate-limit"])
        remaining = int(resp.headers["x-rate-limit-remaining"])
    except (KeyError, TypeError, ValueError):
        return
    if limit > 0 and remaining <= limit * LOW_QUOTA_FRACTION:
        logger.warning(
            "Travelpayouts quota nearly spent: %d of %d left, resets in %ss",
            remaining,
            limit,
            resp.headers.get("x-rate-limit-reset", "?"),
        )


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
            client = _pooled_client()
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

        _log_quota(resp)

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
