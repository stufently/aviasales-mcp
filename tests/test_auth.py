import asyncio

import httpx
import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import PlainTextResponse, StreamingResponse
from starlette.routing import Route

from aviasales_mcp.auth import HostOriginMiddleware, TokenAuthMiddleware

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


@pytest.mark.asyncio
async def test_streamed_responses_pass_through_unbuffered():
    # The MCP transport answers with SSE streams; the guards must hand each
    # chunk on as it is produced rather than collect the body the way
    # BaseHTTPMiddleware does. The second chunk is held back until the first
    # has reached the client, so a buffering guard hangs here instead of
    # passing. The app is driven directly: httpx's ASGITransport buffers too.
    first_seen = asyncio.Event()

    async def events():
        yield b"event: message\n"
        await asyncio.wait_for(first_seen.wait(), timeout=2)
        yield b"data: {}\n\n"

    async def endpoint(request):
        return StreamingResponse(events(), media_type="text/event-stream")

    app = Starlette(
        routes=[Route("/mcp", endpoint)],
        middleware=[
            Middleware(HostOriginMiddleware, allowed_hosts=["testserver"]),
            Middleware(TokenAuthMiddleware, token=TOKEN),
        ],
    )
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/mcp",
        "raw_path": b"/mcp",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"authorization", f"Bearer {TOKEN}".encode()),
        ],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }
    body = []
    delivered = False

    async def receive():
        # One request, then block: StreamingResponse polls receive() for a
        # disconnect for as long as the stream runs.
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()

    async def send(message):
        if message["type"] == "http.response.start":
            assert message["status"] == 200
        elif message["type"] == "http.response.body":
            body.append(message.get("body", b""))
            first_seen.set()

    await app(scope, receive, send)
    assert b"".join(body) == b"event: message\ndata: {}\n\n"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "guard",
    [
        lambda app: TokenAuthMiddleware(app, token=TOKEN),
        lambda app: HostOriginMiddleware(app, allowed_hosts=["127.0.0.1"]),
    ],
)
async def test_lifespan_events_are_not_treated_as_requests(guard):
    # Starlette sends a `lifespan` scope at startup with no headers at all. A
    # guard that inspected it would refuse the server its own startup.
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    await guard(app)({"type": "lifespan"}, None, None)
    assert seen == ["lifespan"]


# --- Host / Origin ---------------------------------------------------------

LOOPBACK = ("127.0.0.1", "localhost", "::1")


def _host_app(allowed=LOOPBACK) -> Starlette:
    async def endpoint(request):
        return PlainTextResponse("ok")

    return Starlette(
        routes=[Route("/mcp", endpoint, methods=["GET", "POST"])],
        middleware=[Middleware(HostOriginMiddleware, allowed_hosts=allowed)],
    )


async def _post(headers: dict, allowed=LOOPBACK) -> httpx.Response:
    transport = httpx.ASGITransport(app=_host_app(allowed))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        return await client.post("/mcp", headers=headers)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host", ["127.0.0.1", "127.0.0.1:8080", "localhost:8080", "LOCALHOST", "[::1]:8080"]
)
async def test_loopback_hosts_are_served(host):
    resp = await _post({"Host": host})
    assert resp.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "host",
    [
        "evil.example",
        "evil.example:8080",
        "127.0.0.1.evil.example",
        "",
        "[::1",
        "evil.example@localhost",
        "localhost/",
        "localhost:8080:1",
    ],
)
async def test_foreign_host_is_refused(host):
    # A DNS-rebound page reaches 127.0.0.1 but still says who it thinks it is.
    resp = await _post({"Host": host})
    assert resp.status_code == 421


@pytest.mark.asyncio
async def test_missing_host_header_is_refused():
    transport = httpx.ASGITransport(app=_host_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        req = client.build_request("POST", "/mcp")
        del req.headers["host"]
        resp = await client.send(req)
    assert resp.status_code == 421


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin",
    [
        "http://evil.example",
        "https://evil.example:8080",
        "null",
        "http://127.0.0.1.evil.example",
        "http://[::1",
        "",
        "//localhost",
        "http://evil.example@localhost",
        "http://localhost/",
        "ftp://localhost",
    ],
)
async def test_foreign_origin_is_refused(origin):
    resp = await _post({"Host": "127.0.0.1:8080", "Origin": origin})
    assert resp.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["http://127.0.0.1:8080", "http://localhost", "http://[::1]:8080"])
async def test_loopback_origin_is_served(origin):
    resp = await _post({"Host": "127.0.0.1:8080", "Origin": origin})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_a_second_foreign_origin_header_is_refused():
    transport = httpx.ASGITransport(app=_host_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        headers = httpx.Headers(
            [("Host", "127.0.0.1"), ("Origin", "http://localhost"), ("Origin", "http://evil.example")]
        )
        resp = await client.post("/mcp", headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_no_origin_header_is_served():
    # Non-browser MCP clients send none; only browsers add it, and only they
    # can be rebound.
    resp = await _post({"Host": "127.0.0.1:8080"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_configured_public_host_is_served_and_others_refused():
    allowed = ["mcp.example.com"]
    assert (await _post({"Host": "mcp.example.com"}, allowed)).status_code == 200
    assert (await _post({"Host": "127.0.0.1"}, allowed)).status_code == 421


@pytest.mark.asyncio
async def test_without_host_check_any_origin_is_refused_and_any_host_served():
    # A public bind behind a proxy whose name is unknown: Host passes, but a
    # browser request (the only kind that carries Origin) does not.
    def app():
        async def endpoint(request):
            return PlainTextResponse("ok")

        return Starlette(
            routes=[Route("/mcp", endpoint, methods=["POST"])],
            middleware=[Middleware(HostOriginMiddleware, allowed_hosts=[], check_host=False)],
        )

    transport = httpx.ASGITransport(app=app())
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        assert (await client.post("/mcp", headers={"Host": "anything.example"})).status_code == 200
        resp = await client.post(
            "/mcp", headers={"Host": "anything.example", "Origin": "http://anything.example"}
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "guard",
    [
        lambda app: TokenAuthMiddleware(app, token=TOKEN),
        lambda app: HostOriginMiddleware(app, allowed_hosts=["127.0.0.1"]),
    ],
)
async def test_websocket_without_credentials_is_closed_not_answered_over_http(guard):
    # No websocket route exists today; if one appears it must not be the one
    # path that skips the guards, and a refusal has to be a close frame.
    sent = []
    reached = []

    async def app(scope, receive, send):
        reached.append(True)

    async def send(message):
        sent.append(message)

    scope = {"type": "websocket", "headers": [(b"host", b"evil.example")], "query_string": b""}
    await guard(app)(scope, None, send)
    assert reached == []
    assert sent == [{"type": "websocket.close", "code": 1008}]
