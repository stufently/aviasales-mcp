"""Shared response shaping for tools.

Two rules the tool modules follow:

* A tool never raises. An exception escaping a tool reaches the model as a
  JSON-RPC protocol error, which it cannot act on, instead of a payload it can
  read and correct.
* An error and an empty result must not look the same. ``{"data": []}`` alone
  reads as "there are no flights on this route" even when the truth is "the API
  rejected your token", so every response carries a ``status`` discriminator and
  failures carry a ``hint`` naming the next thing to try.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any

from aviasales_mcp.api.client import TravelpayoutsError
from aviasales_mcp.validation import InvalidArgumentError

logger = logging.getLogger(__name__)

# Anything other than these two is a bug in this server, not something the model
# said, so its text must not be echoed into the conversation.
_INTERNAL_ERROR = "Internal server error — see server logs"

ErrorBuilder = Callable[[str, str | None], dict[str, Any]]


def guard(build_error: ErrorBuilder, *, hint: str | None = None):
    """Turn every failure inside a tool into an error payload the model can use.

    ``build_error`` shapes the module's own error dict (the reference tools carry
    ``total``/``returned``/``truncated``, the flight tools do not), so the guard
    stays agnostic about payload shape.
    """

    def decorate(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except InvalidArgumentError as exc:
                return build_error(str(exc), None)
            except TravelpayoutsError as exc:
                # Covers RateLimitError too: it is not an ApiError.
                return build_error(str(exc), hint)
            except Exception:
                # A malformed upstream payload should not take the session down,
                # but its exception text may carry internals — log, do not echo.
                logger.exception("Unhandled error in tool %s", fn.__name__)
                return build_error(_INTERNAL_ERROR, hint)

        return wrapper

    return decorate
