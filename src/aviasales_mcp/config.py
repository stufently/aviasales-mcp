from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    aviasales_api_token: SecretStr
    aviasales_partner_id: str = ""
    log_level: str = "INFO"


settings = Settings()
