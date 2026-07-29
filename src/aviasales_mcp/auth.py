"""Shared-secret auth for the optional streamable-HTTP transport.

Only used when the server is exposed over HTTP. The stdio transport is reached
through the client's own process boundary and needs no token of its own.
"""

from __future__ import annotations

import hmac
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Reject every request that does not carry the configured token.

    The token is read from ``Authorization: Bearer <token>``. Query strings are
    written verbatim to uvicorn's access log (and to any proxy in front of it),
    so accepting ``?token=`` leaks the shared secret into logs — it is therefore
    off unless a client that cannot set headers forces it on via
    ``allow_query_token``.
    """

    def __init__(self, app: Any, token: str, allow_query_token: bool = False) -> None:
        super().__init__(app)
        self._token = token.encode("utf-8")
        self._allow_query_token = allow_query_token

    def _presented_token(self, request: Request) -> bytes:
        scheme, _, value = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            return value.strip().encode("utf-8")
        if self._allow_query_token:
            return request.query_params.get("token", "").encode("utf-8")
        return b""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # compare_digest keeps the comparison constant-time, so a wrong token
        # cannot be recovered byte by byte from response timings.
        if not hmac.compare_digest(self._presented_token(request), self._token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)
