from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    app_name: str = "reference-mcp-server"
    synthetic_hris_database_host: str = Field(
        default="synthetic-hris-db", alias="SYNTHETIC_HRIS_DATABASE_HOST"
    )
    synthetic_hris_database_port: int = Field(default=5432, alias="SYNTHETIC_HRIS_DATABASE_PORT")
    synthetic_hris_database_name: str = Field(
        default="synthetic_hris", alias="SYNTHETIC_HRIS_DATABASE_NAME"
    )
    synthetic_hris_database_user: str = Field(
        default="synthetic_hris_app", alias="SYNTHETIC_HRIS_DATABASE_USER"
    )
    synthetic_hris_database_password: str = Field(
        default="", alias="SYNTHETIC_HRIS_DATABASE_PASSWORD"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
