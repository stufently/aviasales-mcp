import httpx
import pytest
import respx

from aviasales_mcp.api import client
from aviasales_mcp.api.client import ApiError, RateLimitError, get

API_BASE = "https://api.travelpayouts.com"
PATH = "/aviasales/v3/prices_for_dates"
OK = {"success": True, "currency": "rub", "data": []}


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch):
    """Keep the retry tests instant — the delays themselves are not under test."""
    monkeypatch.setattr(client, "RETRY_BACKOFF", 0.0)


@respx.mock
@pytest.mark.asyncio
async def test_retries_transient_server_error():
    route = respx.get(f"{API_BASE}{PATH}").mock(
        side_effect=[httpx.Response(502, text="bad gateway"), httpx.Response(200, json=OK)]
    )

    assert await get(PATH) == OK
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_gives_up_after_persistent_server_errors():
    route = respx.get(f"{API_BASE}{PATH}").mock(return_value=httpx.Response(500, text="boom"))

    with pytest.raises(ApiError, match="HTTP 500"):
        await get(PATH)
    assert route.call_count == client.MAX_RETRIES + 1


@respx.mock
@pytest.mark.asyncio
async def test_retries_timeout():
    route = respx.get(f"{API_BASE}{PATH}").mock(
        side_effect=[httpx.TimeoutException("slow"), httpx.Response(200, json=OK)]
    )

    assert await get(PATH) == OK
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_gives_up_after_persistent_timeouts():
    respx.get(f"{API_BASE}{PATH}").mock(side_effect=httpx.TimeoutException("slow"))

    with pytest.raises(ApiError, match="timed out"):
        await get(PATH)


@respx.mock
@pytest.mark.asyncio
async def test_retries_connection_error():
    route = respx.get(f"{API_BASE}{PATH}").mock(
        side_effect=[httpx.ConnectError("refused"), httpx.Response(200, json=OK)]
    )

    assert await get(PATH) == OK
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_unauthorized_is_not_retried():
    route = respx.get(f"{API_BASE}{PATH}").mock(return_value=httpx.Response(401))

    with pytest.raises(ApiError, match="AVIASALES_API_TOKEN"):
        await get(PATH)
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_client_error_is_not_retried():
    route = respx.get(f"{API_BASE}{PATH}").mock(return_value=httpx.Response(404, text="nope"))

    with pytest.raises(ApiError, match="HTTP 404"):
        await get(PATH)
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_rate_limit_is_retried_then_raises():
    route = respx.get(f"{API_BASE}{PATH}").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "0"})
    )

    with pytest.raises(RateLimitError):
        await get(PATH)
    assert route.call_count == client.MAX_RETRIES + 1


@respx.mock
@pytest.mark.asyncio
async def test_rate_limit_recovers_within_retries():
    respx.get(f"{API_BASE}{PATH}").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json=OK),
        ]
    )

    assert await get(PATH) == OK


@pytest.mark.parametrize("header", ["soon", "NaN", "inf", "-inf", "Wed, 21 Oct 2026 07:28:00 GMT"])
@respx.mock
@pytest.mark.asyncio
async def test_garbled_retry_after_header_does_not_crash(header):
    # float("NaN") and float("inf") both survive float(), then asyncio.sleep
    # either raises or parks the call forever.
    respx.get(f"{API_BASE}{PATH}").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": header}),
            httpx.Response(200, json=OK),
        ]
    )

    assert await get(PATH) == OK


def test_retry_after_is_bounded():
    huge = httpx.Response(429, headers={"Retry-After": "86400"})
    assert client._retry_after(huge) == client.MAX_RETRY_DELAY

    negative = httpx.Response(429, headers={"Retry-After": "-10"})
    assert client._retry_after(negative) == 0.0

    sane = httpx.Response(429, headers={"Retry-After": "5"})
    assert client._retry_after(sane) == 5.0


@respx.mock
@pytest.mark.asyncio
async def test_non_json_response_is_reported_clearly():
    respx.get(f"{API_BASE}{PATH}").mock(
        return_value=httpx.Response(200, text="<html>maintenance</html>")
    )

    with pytest.raises(ApiError, match="non-JSON"):
        await get(PATH)


@respx.mock
@pytest.mark.asyncio
async def test_none_params_are_dropped():
    route = respx.get(f"{API_BASE}{PATH}").mock(return_value=httpx.Response(200, json=OK))

    await get(PATH, origin="MOW", destination=None)
    assert route.calls[0].request.url.params == httpx.QueryParams(origin="MOW")
