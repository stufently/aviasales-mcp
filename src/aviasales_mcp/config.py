import os

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# A token is sent as an HTTP header value, so anything outside printable ASCII
# (a trailing newline from a copy-paste, a non-breaking space) makes httpx
# refuse the request with "Illegal header value b'<the whole token>'" — and that
# text used to travel back to the model. Refusing it here keeps the secret out
# of every error path, and says what is wrong without quoting the value.
_PRINTABLE_ASCII = set(range(0x21, 0x7F))


def _clean_secret(value: object, name: str) -> object:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if any(ord(ch) not in _PRINTABLE_ASCII for ch in text):
        raise ValueError(
            f"{name} contains whitespace or non-ASCII characters; "
            "paste the token on one line with nothing around it"
        )
    return text


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Not `.env` from the working directory: MCP clients launch stdio servers
        # with the open project as cwd, and a foreign repository's `.env` could
        # then swap the partner marker or flip the transport to HTTP. A dotenv
        # file is read only when it is named explicitly.
        env_file=os.environ.get("AVIASALES_ENV_FILE") or None,
        env_file_encoding="utf-8",
        extra="ignore",
        # A rejected token must not be quoted back as `input_value=` in the
        # validation error; that traceback ends up in logs and bug reports.
        hide_input_in_errors=True,
    )

    aviasales_api_token: SecretStr
    aviasales_partner_id: str = ""
    log_level: str = "INFO"

    # Defaults for every tool call; each one is still overridable per call.
    aviasales_default_currency: str = "rub"
    # The price cache is per market: LON-NYC in USD comes back at a different
    # price for market=ru than for market=us (verified live). Left empty the API
    # falls back to the ru market, which is wrong for most deployments.
    aviasales_market: str = ""
    # Language of the reference datasets (/data/<locale>/cities.json). Only
    # affects names, not codes.
    aviasales_locale: str = "en"

    # Optional HTTP transport. Left unset the server speaks stdio, which is what
    # local MCP clients expect. Setting a port switches it to streamable-http so
    # it can be reached remotely; PORT is accepted as an alias because most PaaS
    # providers inject it. It comes from the process environment only — a
    # project's `.env` is no longer read by accident (see model_config).
    mcp_host: str = "127.0.0.1"
    mcp_port: int | None = Field(
        default=None,
        validation_alias=AliasChoices("mcp_port", "port"),
    )
    mcp_auth_token: SecretStr | None = None
    # Query strings land in access logs, so the token goes in a header unless a
    # client that cannot set one forces this on.
    mcp_auth_allow_query_token: bool = False
    # Required to bind anywhere but loopback without a token.
    mcp_allow_insecure_http: bool = False
    # Host names (no port) the HTTP transport answers for, comma-separated.
    # A loopback bind always answers to the loopback names and adds these.
    mcp_allowed_hosts: str = ""

    @field_validator("aviasales_api_token", mode="before")
    @classmethod
    def _clean_api_token(cls, value: object) -> object:
        return _clean_secret(value, "AVIASALES_API_TOKEN")

    @field_validator("mcp_auth_token", mode="before")
    @classmethod
    def _clean_auth_token(cls, value: object) -> object:
        cleaned = _clean_secret(value, "MCP_AUTH_TOKEN")
        # A blank value is "no token", not a token made of spaces.
        return cleaned or None

    @property
    def allowed_hosts(self) -> list[str]:
        return [h.strip().lower() for h in self.mcp_allowed_hosts.split(",") if h.strip()]


settings = Settings()
