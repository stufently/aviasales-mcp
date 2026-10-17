"""Settings hygiene: what a token may contain, and where configuration may come from."""

import importlib
import os
import subprocess
import sys

import pytest

from aviasales_mcp import config
from aviasales_mcp.config import Settings


@pytest.fixture
def clean_env(monkeypatch):
    """Only the one required variable, nothing inherited from the host."""
    for name in list(os.environ):
        if name.startswith(("AVIASALES_", "MCP_")) or name == "PORT":
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AVIASALES_API_TOKEN", "clean-token")
    return monkeypatch


def test_api_token_is_stripped(clean_env):
    clean_env.setenv("AVIASALES_API_TOKEN", "  abc123\n")

    assert Settings().aviasales_api_token.get_secret_value() == "abc123"


@pytest.mark.parametrize("bad", ["abc 123", "abc\n123", "abc\t123", "пароль", "abc\x01"])
def test_api_token_with_control_or_non_ascii_is_refused_without_echoing_it(clean_env, bad):
    clean_env.setenv("AVIASALES_API_TOKEN", bad)

    with pytest.raises(ValueError, match="AVIASALES_API_TOKEN") as excinfo:
        Settings()
    # The message explains the problem; the value itself is a secret.
    assert bad.strip() not in str(excinfo.value)


def test_empty_api_token_is_still_accepted(clean_env):
    # The Docker image starts with a placeholder so directories can introspect it.
    clean_env.setenv("AVIASALES_API_TOKEN", "")

    assert Settings().aviasales_api_token.get_secret_value() == ""


def test_auth_token_is_stripped(clean_env):
    clean_env.setenv("MCP_AUTH_TOKEN", " s3cret \n")

    assert Settings().mcp_auth_token.get_secret_value() == "s3cret"


@pytest.mark.parametrize("blank", ["", " ", "\n"])
def test_blank_auth_token_means_no_token(clean_env, blank):
    clean_env.setenv("MCP_AUTH_TOKEN", blank)

    assert Settings().mcp_auth_token is None


def test_auth_token_with_control_characters_is_refused(clean_env):
    clean_env.setenv("MCP_AUTH_TOKEN", "s3c\x01ret")

    with pytest.raises(ValueError, match="MCP_AUTH_TOKEN"):
        Settings()


def test_bare_port_from_the_environment_is_honoured(clean_env):
    # PaaS runtimes (Render, Railway, Cloud Run) inject the port as PORT.
    clean_env.setenv("PORT", "3000")

    assert Settings().mcp_port == 3000


def test_mcp_port_is_honoured(clean_env):
    clean_env.setenv("MCP_PORT", "3000")

    assert Settings().mcp_port == 3000


def test_allowed_hosts_are_split_and_normalised(clean_env):
    clean_env.setenv("MCP_ALLOWED_HOSTS", " MCP.Example.com, ,api.example.com ")

    assert Settings().allowed_hosts == ["mcp.example.com", "api.example.com"]


def test_dotenv_in_the_working_directory_is_ignored(clean_env, tmp_path):
    # A Node project's PORT=3000 used to turn the stdio server launched from
    # that directory into an unauthenticated HTTP one.
    (tmp_path / ".env").write_text(
        "PORT=3000\nMCP_PORT=8080\nAVIASALES_PARTNER_ID=attacker\nMCP_ALLOW_INSECURE_HTTP=true\n"
    )
    clean_env.chdir(tmp_path)

    loaded = Settings()
    assert loaded.mcp_port is None
    assert loaded.aviasales_partner_id == ""
    assert loaded.mcp_allow_insecure_http is False


def test_dotenv_is_read_when_named_explicitly(clean_env, tmp_path):
    env_file = tmp_path / "server.env"
    env_file.write_text("AVIASALES_PARTNER_ID=54321\n")
    clean_env.setenv("AVIASALES_ENV_FILE", str(env_file))

    # env_file is resolved when the module loads, so load it again.
    try:
        reloaded = importlib.reload(config)
        assert reloaded.settings.aviasales_partner_id == "54321"
    finally:
        clean_env.delenv("AVIASALES_ENV_FILE")
        importlib.reload(config)


def test_fastmcp_does_not_read_dotenv_from_the_working_directory(tmp_path):
    # fastmcp has its own settings and its own `.env` habit. A foreign file
    # that expands the token into a FASTMCP_* value used to print the token in
    # the startup traceback. A fresh interpreter, because fastmcp is imported
    # once per process.
    (tmp_path / ".env").write_text("FASTMCP_PORT=${AVIASALES_API_TOKEN}\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("FASTMCP_")}
    env["AVIASALES_API_TOKEN"] = "SECRET-abc123"

    run = subprocess.run(
        [sys.executable, "-c", "import aviasales_mcp.server"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert run.returncode == 0, run.stderr[-500:]
    assert "SECRET-abc123" not in run.stderr
