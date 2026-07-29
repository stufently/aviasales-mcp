import httpx
import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from aviasales_mcp.auth import TokenAuthMiddleware

TOKEN = "s3cret-token"


def _app(token: str = TOKEN, allow_query_token: bool = True) -> Starlette:
    async def endpoint(request):
        return PlainTextResponse("ok")

    return Starlette(
        routes=[Route("/mcp", endpoint)],
        middleware=[
            Middleware(
                TokenAuthMiddleware,
                token=token,
                allow_query_token=allow_query_token,
            )
        ],
    )


async def _get(
    url: str,
    headers: dict | None = None,
    token: str = TOKEN,
    allow_query_token: bool = True,
) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app(token, allow_query_token))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(url, headers=headers or {})


@pytest.mark.asyncio
async def test_request_without_token_is_rejected():
    resp = await _get("/mcp")
    assert resp.status_code == 401
    assert resp.json() == {"error": "unauthorized"}


@pytest.mark.asyncio
async def test_wrong_query_token_is_rejected():
    resp = await _get("/mcp?token=nope")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_correct_query_token_is_accepted():
    resp = await _get(f"/mcp?token={TOKEN}")
    assert resp.status_code == 200
    assert resp.text == "ok"


@pytest.mark.asyncio
async def test_correct_bearer_header_is_accepted():
    resp = await _get("/mcp", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_bearer_scheme_is_case_insensitive():
    resp = await _get("/mcp", headers={"Authorization": f"bearer {TOKEN}"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_wrong_bearer_header_is_rejected():
    resp = await _get("/mcp", headers={"Authorization": "Bearer nope"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_prefix_of_the_token_is_rejected():
    resp = await _get(f"/mcp?token={TOKEN[:-1]}")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_non_ascii_token_does_not_raise():
    # hmac.compare_digest rejects non-ASCII str, so both sides are compared as bytes.
    resp = await _get("/mcp?token=пароль", token="пароль")
    assert resp.status_code == 200

    resp = await _get("/mcp?token=пароль", token=TOKEN)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unknown_paths_are_guarded_too():
    resp = await _get("/anything")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_query_token_is_rejected_when_not_explicitly_allowed():
    # Default posture: the secret must not have to travel in a logged query string.
    resp = await _get(f"/mcp?token={TOKEN}", allow_query_token=False)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bearer_still_works_when_query_tokens_are_disallowed():
    resp = await _get(
        "/mcp",
        headers={"Authorization": f"Bearer {TOKEN}"},
        allow_query_token=False,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_empty_bearer_value_falls_through_to_rejection():
    resp = await _get("/mcp", headers={"Authorization": "Bearer "}, allow_query_token=False)
    assert resp.status_code == 401
