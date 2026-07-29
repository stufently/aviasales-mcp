import logging

import pytest
from pydantic import SecretStr

from aviasales_mcp import server
from aviasales_mcp.auth import TokenAuthMiddleware


@pytest.fixture
def run_kwargs(monkeypatch):
    """Capture what main() would have handed to FastMCP.run."""
    captured: dict = {}

    def fake_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(server.mcp, "run", fake_run)
    return captured


def test_defaults_to_stdio(monkeypatch, run_kwargs):
    monkeypatch.setattr(server.settings, "mcp_port", None)

    server.main()

    assert run_kwargs == {"transport": "stdio"}


def test_serves_http_with_auth_when_token_is_set(monkeypatch, run_kwargs):
    monkeypatch.setattr(server.settings, "mcp_port", 8080)
    monkeypatch.setattr(server.settings, "mcp_host", "0.0.0.0")
    monkeypatch.setattr(server.settings, "mcp_auth_token", SecretStr("s3cret"))

    server.main()

    assert run_kwargs["transport"] == "streamable-http"
    assert run_kwargs["host"] == "0.0.0.0"
    assert run_kwargs["port"] == 8080
    middleware = run_kwargs["middleware"]
    assert len(middleware) == 1
    assert middleware[0].cls is TokenAuthMiddleware
    assert middleware[0].kwargs["allow_query_token"] is False


def test_query_token_can_be_opted_into(monkeypatch, run_kwargs):
    monkeypatch.setattr(server.settings, "mcp_port", 8080)
    monkeypatch.setattr(server.settings, "mcp_auth_token", SecretStr("s3cret"))
    monkeypatch.setattr(server.settings, "mcp_auth_allow_query_token", True)

    server.main()

    assert run_kwargs["middleware"][0].kwargs["allow_query_token"] is True


def test_loopback_without_token_starts_but_warns(monkeypatch, run_kwargs, caplog):
    monkeypatch.setattr(server.settings, "mcp_port", 8080)
    monkeypatch.setattr(server.settings, "mcp_host", "127.0.0.1")
    monkeypatch.setattr(server.settings, "mcp_auth_token", None)

    with caplog.at_level(logging.WARNING, logger=server.logger.name):
        server.main()

    assert run_kwargs["middleware"] is None
    assert "MCP_AUTH_TOKEN" in caplog.text


def test_public_bind_without_token_refuses_to_start(monkeypatch, run_kwargs):
    monkeypatch.setattr(server.settings, "mcp_port", 8080)
    monkeypatch.setattr(server.settings, "mcp_host", "0.0.0.0")
    monkeypatch.setattr(server.settings, "mcp_auth_token", None)
    monkeypatch.setattr(server.settings, "mcp_allow_insecure_http", False)

    with pytest.raises(SystemExit, match="MCP_AUTH_TOKEN"):
        server.main()

    assert run_kwargs == {}


def test_public_bind_without_token_can_be_forced(monkeypatch, run_kwargs, caplog):
    monkeypatch.setattr(server.settings, "mcp_port", 8080)
    monkeypatch.setattr(server.settings, "mcp_host", "0.0.0.0")
    monkeypatch.setattr(server.settings, "mcp_auth_token", None)
    monkeypatch.setattr(server.settings, "mcp_allow_insecure_http", True)

    with caplog.at_level(logging.WARNING, logger=server.logger.name):
        server.main()

    assert run_kwargs["transport"] == "streamable-http"
    assert run_kwargs["middleware"] is None


@pytest.mark.asyncio
async def test_every_tool_is_registered():
    tools = await server.mcp.list_tools()

    assert {tool.name for tool in tools} == {
        "search_flights",
        "get_prices_calendar",
        "get_latest_prices",
        "get_popular_directions",
        "get_alternative_directions",
        "lookup_airlines",
        "lookup_airports",
        "lookup_cities",
        "lookup_countries",
    }
