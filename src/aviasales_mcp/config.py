from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
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
    # providers inject it.
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


settings = Settings()
