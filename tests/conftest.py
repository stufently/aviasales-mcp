import os

# Ensure test env vars are set before any imports touch settings
os.environ.setdefault("AVIASALES_API_TOKEN", "test-token-for-testing")
os.environ.setdefault("AVIASALES_PARTNER_ID", "12345")

import pytest  # noqa: E402

from aviasales_mcp.api import client  # noqa: E402
from aviasales_mcp.tools import reference  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_reference_cache():
    """Keep the per-process dataset cache from leaking between tests."""
    reference._reset_cache()
    yield
    reference._reset_cache()


@pytest.fixture(autouse=True)
async def _close_pooled_http_client():
    """Close this test's pooled client.

    The pool is keyed by event loop and the suite runs a fresh loop per test, so
    without this every test that makes a request leaves an open client behind.
    """
    yield
    await client.aclose()
