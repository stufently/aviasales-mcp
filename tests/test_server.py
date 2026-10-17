import logging
import re

import pytest
from pydantic import SecretStr

from aviasales_mcp import server
from aviasales_mcp.api import client as api_client
from aviasales_mcp.auth import HostOriginMiddleware, TokenAuthMiddleware


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


def _by_class(middleware, cls):
    found = [m for m in middleware if m.cls is cls]
    assert len(found) == 1, [m.cls for m in middleware]
    return found[0]


def test_serves_http_with_auth_when_token_is_set(monkeypatch, run_kwargs):
    monkeypatch.setattr(server.settings, "mcp_port", 8080)
    monkeypatch.setattr(server.settings, "mcp_host", "0.0.0.0")
    monkeypatch.setattr(server.settings, "mcp_auth_token", SecretStr("s3cret"))
    monkeypatch.setattr(server.settings, "mcp_allowed_hosts", "")

    server.main()

    assert run_kwargs["transport"] == "streamable-http"
    assert run_kwargs["host"] == "0.0.0.0"
    assert run_kwargs["port"] == 8080
    middleware = run_kwargs["middleware"]
    # A public bind with no MCP_ALLOWED_HOSTS sits behind a proxy whose name
    # we do not know: Host goes unchecked, but Origin is still refused.
    assert [m.cls for m in middleware] == [HostOriginMiddleware, TokenAuthMiddleware]
    assert middleware[0].kwargs == {"allowed_hosts": [], "check_host": False}
    assert middleware[1].kwargs["allow_query_token"] is False


def test_query_token_can_be_opted_into(monkeypatch, run_kwargs):
    monkeypatch.setattr(server.settings, "mcp_port", 8080)
    monkeypatch.setattr(server.settings, "mcp_auth_token", SecretStr("s3cret"))
    monkeypatch.setattr(server.settings, "mcp_auth_allow_query_token", True)

    server.main()

    auth = _by_class(run_kwargs["middleware"], TokenAuthMiddleware)
    assert auth.kwargs["allow_query_token"] is True


def test_loopback_bind_checks_host_and_origin_before_the_token(monkeypatch, run_kwargs):
    monkeypatch.setattr(server.settings, "mcp_port", 8080)
    monkeypatch.setattr(server.settings, "mcp_host", "127.0.0.1")
    monkeypatch.setattr(server.settings, "mcp_auth_token", SecretStr("s3cret"))
    # A local reverse proxy forwards its public name; it joins the loopback ones.
    monkeypatch.setattr(server.settings, "mcp_allowed_hosts", "mcp.example.com")

    server.main()

    middleware = run_kwargs["middleware"]
    assert [m.cls for m in middleware] == [HostOriginMiddleware, TokenAuthMiddleware]
    assert set(middleware[0].kwargs["allowed_hosts"]) == {
        "127.0.0.1",
        "::1",
        "localhost",
        "mcp.example.com",
    }
    assert middleware[0].kwargs["check_host"] is True


def test_public_bind_checks_the_configured_hosts(monkeypatch, run_kwargs):
    monkeypatch.setattr(server.settings, "mcp_port", 8080)
    monkeypatch.setattr(server.settings, "mcp_host", "0.0.0.0")
    monkeypatch.setattr(server.settings, "mcp_auth_token", SecretStr("s3cret"))
    monkeypatch.setattr(server.settings, "mcp_allowed_hosts", "mcp.example.com, Alt.Example.com")

    server.main()

    middleware = run_kwargs["middleware"]
    assert [m.cls for m in middleware] == [HostOriginMiddleware, TokenAuthMiddleware]
    assert middleware[0].kwargs["allowed_hosts"] == ["mcp.example.com", "alt.example.com"]
    assert middleware[0].kwargs["check_host"] is True


def test_loopback_without_token_starts_but_warns(monkeypatch, run_kwargs, caplog):
    monkeypatch.setattr(server.settings, "mcp_port", 8080)
    monkeypatch.setattr(server.settings, "mcp_host", "127.0.0.1")
    monkeypatch.setattr(server.settings, "mcp_auth_token", None)

    with caplog.at_level(logging.WARNING, logger=server.logger.name):
        server.main()

    # No token, but the Host/Origin guard still stands: without it a web page
    # could rebind its DNS name to 127.0.0.1 and drive the tools.
    assert [m.cls for m in run_kwargs["middleware"]] == [HostOriginMiddleware]
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
    monkeypatch.setattr(server.settings, "mcp_allowed_hosts", "")

    with caplog.at_level(logging.WARNING, logger=server.logger.name):
        server.main()

    assert run_kwargs["transport"] == "streamable-http"
    # Forced open, but a browser-originated request is still turned away.
    assert [m.cls for m in run_kwargs["middleware"]] == [HostOriginMiddleware]
    assert run_kwargs["middleware"][0].kwargs["check_host"] is False


@pytest.mark.asyncio
async def test_every_tool_is_registered():
    tools = await server.mcp.list_tools()

    assert {tool.name for tool in tools} == {
        "search_flights",
        "get_prices_calendar",
        "get_flexible_date_prices",
        "get_latest_prices",
        "get_popular_directions",
        "get_city_directions",
        "get_alternative_directions",
        "search_by_price_range",
        "lookup_airlines",
        "lookup_airports",
        "lookup_cities",
        "lookup_countries",
        "find_nearest_airports",
    }


@pytest.mark.asyncio
async def test_tools_are_annotated_read_only():
    # Lets a host auto-approve these calls instead of prompting for each one.
    for tool in await server.mcp.list_tools():
        assert tool.annotations is not None, tool.name
        assert tool.annotations.readOnlyHint is True, tool.name
        assert tool.annotations.destructiveHint is False, tool.name
        # Every answer comes from a remote API, not from this process.
        assert tool.annotations.openWorldHint is True, tool.name
        # Same arguments, same cached answer: a host may retry without asking.
        assert tool.annotations.idempotentHint is True, tool.name


@pytest.mark.asyncio
async def test_decorated_tools_keep_their_schema():
    # The tool functions are wrapped by the error guard; if the wrapper hid the
    # signature, the model would see a tool with no arguments.
    tools = {tool.name: tool for tool in await server.mcp.list_tools()}

    schema = tools["search_flights"].parameters
    props = schema["properties"]
    assert set(schema["required"]) == {"origin", "destination"}
    assert "depart_after" in props
    assert props["limit"]["maximum"] == 100
    # Enums must reach the model through the schema, not only the docstring.
    assert set(props["trip_class"]["enum"]) == {"economy", "comfort", "business", "first"}
    assert "IATA" in tools["search_flights"].description


@pytest.mark.asyncio
async def test_tool_descriptions_say_when_to_call_them():
    # The description is the only text the model sees when choosing a tool.
    for tool in await server.mcp.list_tools():
        description = tool.description or ""
        # `Use when` opens its own sentence, after the one-line summary.
        assert re.search(r"(?:^|[.!?]\s+)Use when ", description), tool.name
        assert not description.startswith("Use when"), tool.name
        assert len(description.split()) >= 25, (tool.name, len(description.split()))


@pytest.mark.asyncio
async def test_tool_descriptions_point_only_at_real_tools():
    # A renamed tool must not leave a sibling telling the model to call a ghost.
    tools = await server.mcp.list_tools()
    names = {tool.name for tool in tools}
    for tool in tools:
        description = tool.description or ""
        mentioned = set(re.findall(r"`([a-z]+(?:_[a-z]+)+)`", description))
        referenced = {
            name for name in mentioned if name.split("_")[0] in {"search", "get", "lookup", "find"}
        }
        assert referenced <= names, (tool.name, referenced - names)
        assert tool.name not in referenced, tool.name


@pytest.mark.asyncio
async def test_lifespan_closes_the_pooled_http_client():
    pooled = api_client._pooled_client()
    assert not pooled.is_closed

    async with server._lifespan(server.mcp):
        pass

    assert pooled.is_closed


@pytest.mark.asyncio
async def test_server_reports_a_version():
    # Clients cache tool definitions and need something to invalidate on.
    assert server.__version__
    assert server.mcp.version == server.__version__
