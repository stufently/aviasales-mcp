"""Request guards for the optional streamable-HTTP transport.

Only used when the server is exposed over HTTP. The stdio transport is reached
through the client's own process boundary and needs none of this.

Both guards are plain ASGI callables rather than ``BaseHTTPMiddleware``: that
base class runs the downstream app in a background task and buffers its
response, which does not sit well with the SSE streams the MCP transport sends.
"""

from __future__ import annotations

import hmac
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

_GUARDED_SCOPES = ("http", "websocket")


async def _reject(response: Response, scope: Scope, receive: Receive, send: Send) -> None:
    """Send a refusal: the response itself over HTTP, a policy-violation close on a socket."""
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": 1008})
        return
    await response(scope, receive, send)


def _hostname(url: str | None) -> str:
    """Lower-cased host of a URL, port and IPv6 brackets removed; "" if unparseable."""
    if not url:
        return ""
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return ""


class HostOriginMiddleware:
    """Refuse requests addressed to a host this server does not serve.

    A browser tab on a hostile site can rebind its DNS name to 127.0.0.1 and
    then talk to a loopback MCP server as if it were same-origin. The request
    still carries that site's name in ``Host`` (and ``Origin`` on a POST), which
    is what this checks — the MCP spec requires it, and the fastmcp transport
    does not do it on its own.
    """

    def __init__(
        self, app: ASGIApp, allowed_hosts: Iterable[str], check_host: bool = True
    ) -> None:
        self._app = app
        self._allowed = {h.lower() for h in allowed_hosts}
        # Behind a reverse proxy the public name is whatever the proxy forwards
        # and may be unknown here; Origin is still checked, because only a
        # browser sends one and only a browser can be rebound.
        self._check_host = check_host

    def _rejection(self, scope: Scope) -> PlainTextResponse | None:
        headers = Headers(scope=scope)
        host = headers.get("host")
        if self._check_host and _hostname(f"//{host}" if host else None) not in self._allowed:
            return PlainTextResponse("Invalid Host header", status_code=421)
        origin = headers.get("origin")
        if origin is not None and _hostname(origin) not in self._allowed:
            return PlainTextResponse("Invalid Origin header", status_code=403)
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in _GUARDED_SCOPES:
            rejection = self._rejection(scope)
            if rejection is not None:
                await _reject(rejection, scope, receive, send)
                return
        await self._app(scope, receive, send)


class TokenAuthMiddleware:
    """Reject every request that does not carry the configured token.

    The token is read from ``Authorization: Bearer <token>``. Query strings are
    written verbatim to uvicorn's access log (and to any proxy in front of it),
    so accepting ``?token=`` leaks the shared secret into logs — it is therefore
    off unless a client that cannot set headers forces it on via
    ``allow_query_token``.
    """

    def __init__(self, app: Any, token: str, allow_query_token: bool = False) -> None:
        self._app = app
        self._token = token.encode("utf-8")
        self._allow_query_token = allow_query_token

    def _presented_token(self, conn: HTTPConnection) -> bytes:
        scheme, _, value = conn.headers.get("Authorization", "").partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip().encode("utf-8")
        if self._allow_query_token:
            return conn.query_params.get("token", "").encode("utf-8")
        return b""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in _GUARDED_SCOPES:
            # compare_digest keeps the comparison constant-time, so a wrong token
            # cannot be recovered byte by byte from response timings.
            presented = self._presented_token(HTTPConnection(scope))
            if not hmac.compare_digest(presented, self._token):
                response = JSONResponse({"error": "unauthorized"}, status_code=401)
                await _reject(response, scope, receive, send)
                return
        await self._app(scope, receive, send)
